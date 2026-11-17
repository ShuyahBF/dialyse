"""Postes de dialyse (générateurs / machines) : état, isolement sérologique (VHB / VHC / VIH), maintenance."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from . import db, historique, roles, validation
from .auth import exiger_roles, journaliser, utilisateur_courant

routeur = APIRouter()
STATUTS = ["actif", "maintenance", "hors_service"]
LIBELLE_STATUT = {"actif": "En service", "maintenance": "En maintenance", "hors_service": "Hors service"}
TYPES_MAINTENANCE = ["Préventive", "Corrective", "Désinfection", "Contrôle de l'eau", "Autre"]


def _public(p: dict) -> dict:
    d = {k: v for k, v in p.items() if k != "_id"}
    d["statut_libelle"] = LIBELLE_STATUT.get(d.get("statut", ""), d.get("statut", ""))
    return d


def _valider(corps: dict, creation: bool) -> dict:
    d: dict = {}
    if creation or "nom" in corps:
        d["nom"] = validation.texte(corps, "nom", "Nom du poste", True, 40)
    for cle, lib in (("salle", "Salle"), ("marque", "Marque"), ("modele", "Modèle"), ("numero_serie", "N° de série"), ("remarques", "Remarques")):
        if cle in corps:
            d[cle] = validation.texte(corps, cle, lib, False, 200)
    if "statut" in corps:
        d["statut"] = validation.choix(corps, "statut", "État", STATUTS, obligatoire=True)
    if "isolement" in corps:
        d["isolement"] = bool(corps["isolement"])
    if "prochaine_maintenance" in corps:
        d["prochaine_maintenance"] = validation.date_iso(corps, "prochaine_maintenance", "Prochaine maintenance")
    return d


@routeur.get("/postes")
def lister(u: dict = Depends(exiger_roles(roles.LECTURE_POSTE))):
    """Tous les postes, par nom."""
    return [_public(p) for p in db.base().postes.find({}).sort("nom", 1)]


@routeur.get("/postes/types-maintenance")
def types_maintenance(u: dict = Depends(utilisateur_courant)):
    return {"types": TYPES_MAINTENANCE, "statuts": [{"valeur": s, "libelle": LIBELLE_STATUT[s]} for s in STATUTS]}


@routeur.post("/postes")
def creer(corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_POSTE))):
    """Crée un poste (le nom est unique)."""
    d = _valider(corps, True)
    if db.base().postes.find_one({"nom": d["nom"]}):
        raise HTTPException(409, "Un poste porte déjà ce nom")
    doc = {"id": str(uuid.uuid4()), "statut": "actif", "isolement": False, "maintenances": [], **d,
           "created_at": db.maintenant(), "cree_par": u["login"], "updated_at": db.maintenant(), "maj_par": u["login"]}
    db.base().postes.insert_one(doc)
    journaliser("poste_cree", u, doc["nom"])
    return _public(doc)


@routeur.put("/postes/{id_}")
def modifier(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_POSTE))):
    """Modifie un poste. Passer en maintenance ou hors service est refusé tant qu'une séance EN COURS l'utilise."""
    p = db.base().postes.find_one({"id": id_})
    if not p:
        raise HTTPException(404, "Poste introuvable")
    maj = _valider(corps, False)
    if "nom" in maj and maj["nom"] != p["nom"] and db.base().postes.find_one({"nom": maj["nom"]}):
        raise HTTPException(409, "Un poste porte déjà ce nom")
    if maj.get("statut") in ("maintenance", "hors_service") and db.base().seances.find_one({"poste_id": id_, "statut": "en_cours"}):
        raise HTTPException(409, "Une séance est en cours sur ce poste")
    ch = historique.champs_modifies(p, maj)
    if ch:
        maj.update({"updated_at": db.maintenant(), "maj_par": u["login"]})
        db.base().postes.update_one({"id": id_}, {"$set": maj})
        historique.noter("postes", id_, u, ch)
        journaliser("poste_modifie", u, f"{p['nom']} : {', '.join(sorted(ch))}")
    return _public(db.base().postes.find_one({"id": id_}))


@routeur.post("/postes/{id_}/maintenance")
def enregistrer_maintenance(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_POSTE))):
    """Ajoute une intervention au carnet de maintenance du poste (et met à jour la date de dernière maintenance)."""
    p = db.base().postes.find_one({"id": id_})
    if not p:
        raise HTTPException(404, "Poste introuvable")
    m = {"id": str(uuid.uuid4()), "date": validation.date_iso(corps, "date", "Date", True),
         "type": validation.choix(corps, "type", "Type d'intervention", TYPES_MAINTENANCE, obligatoire=True),
         "remarque": validation.texte(corps, "remarque", "Remarque", False, 300), "par": u["login"]}
    maj = {"derniere_maintenance": max(m["date"], p.get("derniere_maintenance", "")), "updated_at": db.maintenant(), "maj_par": u["login"]}
    if corps.get("prochaine"):
        maj["prochaine_maintenance"] = validation.date_iso(corps, "prochaine", "Prochaine maintenance")
    db.base().postes.update_one({"id": id_}, {"$push": {"maintenances": m}, "$set": maj})
    journaliser("maintenance_ajoutee", u, f"{p['nom']} ({m['type']})")
    return m


@routeur.delete("/postes/{id_}")
def supprimer(id_: str, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Supprime un poste sans aucune séance ; sinon le mettre « hors service »."""
    p = db.base().postes.find_one({"id": id_})
    if not p:
        raise HTTPException(404, "Poste introuvable")
    if db.base().seances.count_documents({"poste_id": id_}) > 0:
        raise HTTPException(409, "Ce poste a des séances : passez-le « hors service » au lieu de le supprimer")
    db.base().postes.delete_one({"id": id_})
    journaliser("poste_supprime", u, p["nom"])
    return {"ok": True}
