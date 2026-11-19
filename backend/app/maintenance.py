"""
MAINTENANCE des postes de dialyse : interventions planifiées (préventive, corrective, désinfection, sécurité électrique, étalonnage), suivi des retards et du compteur de séances.

Cycle : planifiée → en cours (le poste passe « en maintenance » : aucune séance ne peut y être placée) → terminée (le poste revient « en service », le carnet du poste est complété,
la prochaine maintenance est recalculée) ; ou annulée. Un poste ne passe pas en maintenance pendant une séance en cours. Compteur : nombre de séances terminées depuis la dernière
intervention PRÉVENTIVE (seuils réglables dans le code, à valider avec le technicien biomédical).
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from . import db, roles, validation
from .postes import TYPES_MAINTENANCE as TYPES_CARNET
from .auth import exiger_roles, journaliser

routeur = APIRouter()

TYPES = ["Maintenance préventive", "Maintenance corrective (panne)", "Désinfection chimique", "Désinfection thermique", "Contrôle de sécurité électrique", "Étalonnage / contrôle des alarmes", "Remplacement de pièce", "Autre"]
STATUTS = ["planifiee", "en_cours", "terminee", "annulee"]
LIBELLE = {"planifiee": "Planifiée", "en_cours": "En cours", "terminee": "Terminée", "annulee": "Annulée"}
SEUIL_SEANCES_PREVENTIF = 500          # une maintenance préventive est « à prévoir » après 500 séances terminées sur le poste…
SEUIL_JOURS_PREVENTIF = 180            # … ou 180 jours après la dernière
LECTURE = roles.LECTURE_POSTE
ECRITURE = roles.ECRITURE_POSTE


def _public(i: dict, postes: dict) -> dict:
    d = {k: v for k, v in i.items() if k not in ("_id", "centre_id")}
    d["poste_nom"] = (postes.get(i["poste_id"]) or {}).get("nom", "?")
    d["statut_libelle"] = LIBELLE.get(i["statut"], i["statut"])
    d["en_retard"] = i["statut"] == "planifiee" and i["date_prevue"] < date.today().isoformat()
    return d


def _intervention(id_: str) -> dict:
    i = db.base().interventions.find_one({"id": id_})
    if not i:
        raise HTTPException(404, "Intervention introuvable")
    return i


def _recalculer_prochaine(poste_id: str) -> None:
    """La « prochaine maintenance » du poste = la plus proche intervention planifiée (vide s'il n'y en a plus) : le calendrier d'activité l'affiche."""
    prochaine = min((i["date_prevue"] for i in db.base().interventions.find({"poste_id": poste_id, "statut": "planifiee"}, {"date_prevue": 1})), default="")
    db.base().postes.update_one({"id": poste_id}, {"$set": {"prochaine_maintenance": prochaine}})


@routeur.get("/maintenance/listes")
def listes(u: dict = Depends(exiger_roles(LECTURE))):
    return {"types": TYPES, "statuts": [{"valeur": s, "libelle": LIBELLE[s]} for s in STATUTS]}


@routeur.get("/maintenance")
def lister(statut: str = "", poste_id: str = "", u: dict = Depends(exiger_roles(LECTURE))):
    f = {k: v for k, v in (("statut", statut), ("poste_id", poste_id)) if v}
    postes = {p["id"]: p for p in db.base().postes.find({}, {"_id": 0, "id": 1, "nom": 1})}
    return [_public(i, postes) for i in db.base().interventions.find(f).sort("date_prevue", 1).limit(500)]


@routeur.post("/maintenance")
def planifier(corps: dict, u: dict = Depends(exiger_roles(ECRITURE))):
    p = db.base().postes.find_one({"id": str(corps.get("poste_id") or "")})
    if not p:
        raise HTTPException(404, "Poste introuvable")
    doc = {"id": str(uuid.uuid4()), "poste_id": p["id"], "type": validation.choix(corps, "type", "Type d'intervention", TYPES, obligatoire=True),
           "date_prevue": validation.date_iso(corps, "date_prevue", "Date prévue", True), "statut": "planifiee", "prestataire": validation.texte(corps, "prestataire", "Prestataire", False, 100),
           "cout": 0, "notes": validation.texte(corps, "notes", "Notes", False, 300), "cree_par": u["login"], "cree_le": db.maintenant()}
    db.base().interventions.insert_one(doc)
    _recalculer_prochaine(p["id"])
    journaliser("maintenance_planifiee", u, f"{p['nom']} {doc['date_prevue']}")
    return _public(doc, {p["id"]: p})


@routeur.post("/maintenance/{id_}/demarrer")
def demarrer(id_: str, u: dict = Depends(exiger_roles(ECRITURE))):
    """Début de l'intervention : le poste passe « en maintenance ». Refusé si une séance est en cours dessus ; signale les séances encore planifiées ce jour-là."""
    i = _intervention(id_)
    if i["statut"] != "planifiee":
        raise HTTPException(409, "Cette intervention n'est plus planifiée")
    if db.base().seances.find_one({"poste_id": i["poste_id"], "statut": "en_cours"}):
        raise HTTPException(409, "Une séance est en cours sur ce poste")
    a_deplacer = db.base().seances.count_documents({"poste_id": i["poste_id"], "date": date.today().isoformat(), "statut": "planifiee"})
    db.base().interventions.update_one({"id": id_}, {"$set": {"statut": "en_cours", "debut_le": db.maintenant()}})
    db.base().postes.update_one({"id": i["poste_id"]}, {"$set": {"statut": "maintenance"}})
    journaliser("maintenance_demarree", u, id_)
    return {"ok": True, "seances_a_deplacer": a_deplacer}


@routeur.post("/maintenance/{id_}/terminer")
def terminer(id_: str, corps: dict, u: dict = Depends(exiger_roles(ECRITURE))):
    """Fin de l'intervention : coût et durée, carnet du poste complété, poste remis « en service », prochaine maintenance recalculée."""
    i = _intervention(id_)
    if i["statut"] not in ("planifiee", "en_cours"):
        raise HTTPException(409, "Cette intervention est déjà close")
    fait = validation.date_iso(corps, "date_realisee", "Date de réalisation", False) or date.today().isoformat()
    cout = validation.nombre(corps, "cout", "Coût (FCFA)", 0, 100_000_000) or 0
    maj = {"statut": "terminee", "date_realisee": fait, "cout": int(cout), "duree_h": validation.nombre(corps, "duree_h", "Durée (heures)", 0, 500),
           "notes": validation.texte(corps, "notes", "Notes", False, 300) or i.get("notes", ""), "termine_par": u["login"]}
    db.base().interventions.update_one({"id": id_}, {"$set": maj})
    poste = db.base().postes.find_one({"id": i["poste_id"]})
    carnet = {"id": str(uuid.uuid4()), "date": fait, "type": i["type"] if i["type"] in TYPES_CARNET else "Autre",
              "remarque": f"Intervention {i['id'][:8]} : {maj['notes']}"[:300], "par": u["login"]}
    sets = {"derniere_maintenance": max(fait, (poste or {}).get("derniere_maintenance", ""))}
    if i["type"] == "Maintenance préventive":
        sets["derniere_preventive"] = fait
    if (poste or {}).get("statut") == "maintenance":
        sets["statut"] = "actif"
    db.base().postes.update_one({"id": i["poste_id"]}, {"$set": sets, "$push": {"maintenances": carnet}})
    _recalculer_prochaine(i["poste_id"])
    journaliser("maintenance_terminee", u, id_)
    return {"ok": True}


@routeur.post("/maintenance/{id_}/annuler")
def annuler(id_: str, u: dict = Depends(exiger_roles(ECRITURE))):
    i = _intervention(id_)
    if i["statut"] not in ("planifiee", "en_cours"):
        raise HTTPException(409, "Cette intervention est déjà close")
    db.base().interventions.update_one({"id": id_}, {"$set": {"statut": "annulee"}})
    if i["statut"] == "en_cours":
        db.base().postes.update_one({"id": i["poste_id"], "statut": "maintenance"}, {"$set": {"statut": "actif"}})
    _recalculer_prochaine(i["poste_id"])
    journaliser("maintenance_annulee", u, id_)
    return {"ok": True}


@routeur.get("/maintenance/etat")
def etat(u: dict = Depends(exiger_roles(LECTURE))):
    """Par poste : état, dernière / prochaine maintenance, séances depuis la dernière préventive, « à prévoir » ; plus les interventions en retard. Lectures en bloc."""
    auj = date.today().isoformat()
    postes = list(db.base().postes.find({}, {"_id": 0}).sort("nom", 1))
    par_poste: dict = {}
    for s in db.base().seances.find({"statut": "terminee"}, {"_id": 0, "poste_id": 1, "date": 1}):
        par_poste.setdefault(s["poste_id"], []).append(s["date"])
    lignes = []
    for p in postes:
        depuis = p.get("derniere_preventive") or p.get("created_at", "")[:10] or "0000-00-00"
        n = sum(1 for d in par_poste.get(p["id"], []) if d > depuis)
        jours = (date.today() - date.fromisoformat(depuis)).days if depuis[:4].isdigit() and depuis > "0000" else 0
        lignes.append({"poste_id": p["id"], "poste_nom": p["nom"], "statut": p.get("statut"), "derniere": p.get("derniere_maintenance", ""), "prochaine": p.get("prochaine_maintenance", ""),
                       "seances_depuis_preventive": n, "jours_depuis_preventive": jours,
                       "a_prevoir": p.get("statut") != "hors_service" and (n >= SEUIL_SEANCES_PREVENTIF or jours >= SEUIL_JOURS_PREVENTIF) and not p.get("prochaine_maintenance")})
    postes_d = {p["id"]: p for p in postes}
    retard = [_public(i, postes_d) for i in db.base().interventions.find({"statut": "planifiee", "date_prevue": {"$lt": auj}}).sort("date_prevue", 1)]
    return {"postes": lignes, "en_retard": retard, "seuils": {"seances": SEUIL_SEANCES_PREVENTIF, "jours": SEUIL_JOURS_PREVENTIF}}


def a_traiter() -> int:
    """Pastille du menu : interventions planifiées dont la date est arrivée ou dépassée (à démarrer)."""
    auj = date.today().isoformat()
    return db.base().interventions.count_documents({"statut": "planifiee", "date_prevue": {"$lte": auj}})
