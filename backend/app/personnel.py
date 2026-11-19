"""
Planning du PERSONNEL du centre : équipe, affectations par jour et par créneau, absences, couverture des séances.

- L'équipe (`personnel`) et les affectations (`affectations`) sont propres à chaque centre.
- COUVERTURE : pour chaque jour et créneau, le serveur compare le nombre de séances prévues au nombre d'infirmiers / aides-soignants affectés (règle : 1 soignant pour
  `patients_par_infirmier` patients, 4 par défaut, réglable) et vérifie la présence d'un médecin ; un manque est une ALERTE (pastille du menu), jamais un blocage.
- Un salarié absent (congé, maladie, formation) ne peut pas être affecté ce créneau-là. Le coût mensuel d'un salarié n'est visible que de l'administration et de la direction.
"""
from __future__ import annotations

import math
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from . import db, patients as pat, roles, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()

FONCTIONS = ["Néphrologue", "Infirmier(ère)", "Aide-soignant(e)", "Technicien biomédical", "Secrétaire", "Agent d'entretien", "Autre"]
SOIGNANTS = {"Infirmier(ère)", "Aide-soignant(e)"}
TYPES = ["present", "conge", "maladie", "formation"]
LIBELLE_TYPE = {"present": "Présent", "conge": "Congé", "maladie": "Maladie", "formation": "Formation"}
CRENEAUX_AFFECTATION = pat.CRENEAUX + ["journee"]            # « journée » = absence sur les trois créneaux
GESTION = {roles.ADMIN, roles.SUPER_ADMIN, roles.MEDECIN}
LECTURE = set(roles.TOUS_LES_ROLES)
VOIT_COUTS = {roles.ADMIN, roles.SUPER_ADMIN, roles.DIRECTION}
MAX_JOURS = 42
PAR_DEFAUT = 4                                               # patients par infirmier


def _public(p: dict, role: str) -> dict:
    d = {k: v for k, v in p.items() if k not in ("_id", "centre_id")}
    if role not in VOIT_COUTS:
        d.pop("cout_mensuel", None)
    return d


def _regle() -> int:
    return int((db.base().parametres.find_one({"id": "personnel_regles"}) or {}).get("patients_par_infirmier", PAR_DEFAUT))


def _creneaux_couverts(creneau: str) -> set:
    return set(pat.CRENEAUX) if creneau == "journee" else {creneau}


# ---------- équipe ----------

@routeur.get("/personnel/listes")
def listes(u: dict = Depends(exiger_roles(LECTURE))):
    return {"fonctions": FONCTIONS, "types": [{"valeur": t, "libelle": LIBELLE_TYPE[t]} for t in TYPES], "creneaux": pat.CRENEAUX, "regle": _regle()}


@routeur.get("/personnel")
def lister(actifs: bool = True, u: dict = Depends(exiger_roles(LECTURE))):
    f = {"actif": True} if actifs else {}
    return [_public(p, u["role"]) for p in db.base().personnel.find(f).sort([("fonction", 1), ("nom", 1)])]


def _valider(corps: dict, creation: bool) -> dict:
    d: dict = {}
    if creation or "nom" in corps:
        d["nom"] = validation.texte(corps, "nom", "Nom", True, 100)
    if creation or "fonction" in corps:
        d["fonction"] = validation.choix(corps, "fonction", "Fonction", FONCTIONS, obligatoire=True)
    if "telephone" in corps:
        d["telephone"] = validation.texte(corps, "telephone", "Téléphone", False, 30)
    if "cout_mensuel" in corps:
        v = validation.nombre(corps, "cout_mensuel", "Coût mensuel (FCFA)", 0, 100_000_000)
        d["cout_mensuel"] = int(v) if v is not None else 0
    if "actif" in corps:
        d["actif"] = bool(corps["actif"])
    return d


@routeur.post("/personnel")
def creer(corps: dict, u: dict = Depends(exiger_roles(GESTION))):
    d = _valider(corps, True)
    if u["role"] not in VOIT_COUTS:
        d.pop("cout_mensuel", None)
    doc = {"id": str(uuid.uuid4()), "actif": True, "cout_mensuel": 0, **d, "cree_le": db.maintenant()}
    db.base().personnel.insert_one(doc)
    journaliser("personnel_cree", u, doc["id"])
    return _public(doc, u["role"])


@routeur.put("/personnel/regles")
def regler(corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    n = validation.nombre(corps, "patients_par_infirmier", "Patients par infirmier", 1, 12)
    db.base().parametres.update_one({"id": "personnel_regles"}, {"$set": {"patients_par_infirmier": int(n or PAR_DEFAUT)}}, upsert=True)
    journaliser("personnel_regle_modifiee", u, str(n))
    return {"patients_par_infirmier": _regle()}


@routeur.put("/personnel/{id_}")
def modifier(id_: str, corps: dict, u: dict = Depends(exiger_roles(GESTION))):
    if not db.base().personnel.find_one({"id": id_}):
        raise HTTPException(404, "Membre de l'équipe introuvable")
    d = _valider(corps, False)
    if u["role"] not in VOIT_COUTS:
        d.pop("cout_mensuel", None)
    if d:
        db.base().personnel.update_one({"id": id_}, {"$set": d})
    return _public(db.base().personnel.find_one({"id": id_}), u["role"])


# ---------- affectations et absences ----------

def _conflit(personnel_id: str, jour: str, creneau: str, type_: str, sauf: str = "") -> str:
    """Message d'erreur si l'affectation est impossible (déjà affecté ce créneau, ou absent), sinon chaîne vide."""
    voulus = _creneaux_couverts(creneau)
    for a in db.base().affectations.find({"personnel_id": personnel_id, "date": jour}):
        if a["id"] == sauf:
            continue
        if voulus & _creneaux_couverts(a["creneau"]):
            if a["type"] != "present":
                return f"Déjà absent ({LIBELLE_TYPE[a['type']].lower()}) à ce créneau"
            if type_ != "present":
                return "Déjà affecté à ce créneau : retirez d'abord l'affectation"
            return "Déjà affecté à ce créneau"
    return ""


@routeur.post("/personnel/affectations")
def affecter(corps: dict, u: dict = Depends(exiger_roles(GESTION))):
    p = db.base().personnel.find_one({"id": str(corps.get("personnel_id") or "")})
    if not p or not p.get("actif", True):
        raise HTTPException(404, "Membre de l'équipe introuvable ou inactif")
    jour = validation.date_iso(corps, "date", "Date", True)
    type_ = validation.choix(corps, "type", "Type", TYPES, defaut="present")
    creneau = validation.choix(corps, "creneau", "Créneau", CRENEAUX_AFFECTATION, obligatoire=True)
    if type_ == "present" and creneau == "journee":
        validation.erreur("Une présence se place sur un créneau précis (matin, midi ou soir)")
    erreur = _conflit(p["id"], jour, creneau, type_)
    if erreur:
        raise HTTPException(409, erreur)
    doc = {"id": str(uuid.uuid4()), "personnel_id": p["id"], "date": jour, "creneau": creneau, "type": type_, "note": validation.texte(corps, "note", "Note", False, 200),
           "cree_par": u["login"], "cree_le": db.maintenant()}
    db.base().affectations.insert_one(doc)
    journaliser("affectation_creee", u, f"{jour} {creneau} {type_}")
    return {k: v for k, v in doc.items() if k != "_id"}


@routeur.delete("/personnel/affectations/{id_}")
def retirer(id_: str, u: dict = Depends(exiger_roles(GESTION))):
    if not db.base().affectations.find_one({"id": id_}):
        raise HTTPException(404, "Affectation introuvable")
    db.base().affectations.delete_one({"id": id_})
    journaliser("affectation_retiree", u, id_)
    return {"ok": True}


# ---------- planning et couverture ----------

def couverture(du: str, au: str) -> tuple[list[dict], list[dict]]:
    """(affectations de la période avec nom et fonction, couverture jour × créneau). Trois lectures en bloc (règle 7)."""
    equipe = {p["id"]: p for p in db.base().personnel.find({})}
    affs = [a for a in db.base().affectations.find({"date": {"$gte": du, "$lte": au}}, {"_id": 0, "centre_id": 0})]
    seances: dict = {}
    for s in db.base().seances.find({"date": {"$gte": du, "$lte": au}, "statut": {"$nin": ["annulee", "absente"]}}, {"_id": 0, "date": 1, "creneau": 1}):
        seances[(s["date"], s["creneau"])] = seances.get((s["date"], s["creneau"]), 0) + 1
    regle = _regle()
    cases, d = [], date.fromisoformat(du)
    while d <= date.fromisoformat(au):
        jour = d.isoformat()
        for c in pat.CRENEAUX:
            presents = [a for a in affs if a["date"] == jour and a["type"] == "present" and a["creneau"] == c and a["personnel_id"] in equipe]
            soignants = sum(1 for a in presents if equipe[a["personnel_id"]]["fonction"] in SOIGNANTS)
            medecins = sum(1 for a in presents if equipe[a["personnel_id"]]["fonction"] == "Néphrologue")
            n = seances.get((jour, c), 0)
            requis = math.ceil(n / regle) if n else 0
            cases.append({"date": jour, "creneau": c, "seances": n, "soignants": soignants, "medecins": medecins, "soignants_requis": requis,
                          "manque_soignants": max(0, requis - soignants), "sans_medecin": bool(n and not medecins)})
        d += timedelta(days=1)
    lignes = [a | {"personnel_nom": equipe[a["personnel_id"]]["nom"], "fonction": equipe[a["personnel_id"]]["fonction"]} for a in affs if a["personnel_id"] in equipe]
    return lignes, cases


def creneaux_sous_dotes(jours: int = 7) -> int:
    """Nombre de créneaux des prochains jours (aujourd'hui compris) qui ont des séances mais pas assez de soignants ou pas de médecin (pastille du menu)."""
    auj = date.today()
    _, cases = couverture(auj.isoformat(), (auj + timedelta(days=jours - 1)).isoformat())
    return sum(1 for c in cases if c["manque_soignants"] or c["sans_medecin"])


@routeur.get("/personnel/planning")
def planning(du: str, au: str, u: dict = Depends(exiger_roles(LECTURE))):
    du, au = validation.date_iso({"d": du}, "d", "Du", True), validation.date_iso({"d": au}, "d", "Au", True)
    if au < du or (date.fromisoformat(au) - date.fromisoformat(du)).days >= MAX_JOURS:
        validation.erreur(f"Période invalide (de 1 à {MAX_JOURS} jours)")
    lignes, cases = couverture(du, au)
    return {"du": du, "au": au, "regle": _regle(), "affectations": lignes, "couverture": cases}


@routeur.post("/personnel/planning/dupliquer")
def dupliquer(corps: dict, u: dict = Depends(exiger_roles(GESTION))):
    """Recopie les PRÉSENCES d'une semaine (lundi → dimanche) sur une autre ; les doublons et les absences sont respectés (ces lignes sont comptées « ignorées »)."""
    src = validation.date_iso(corps, "du", "Semaine à copier (lundi)", True)
    dst = validation.date_iso(corps, "vers", "Vers la semaine du (lundi)", True)
    decalage = (date.fromisoformat(dst) - date.fromisoformat(src)).days
    if decalage == 0:
        validation.erreur("La semaine d'arrivée doit être différente")
    fin = (date.fromisoformat(src) + timedelta(days=6)).isoformat()
    copiees = ignorees = 0
    for a in list(db.base().affectations.find({"date": {"$gte": src, "$lte": fin}, "type": "present"})):
        jour = (date.fromisoformat(a["date"]) + timedelta(days=decalage)).isoformat()
        p = db.base().personnel.find_one({"id": a["personnel_id"]})
        if not p or not p.get("actif", True) or _conflit(a["personnel_id"], jour, a["creneau"], "present"):
            ignorees += 1
            continue
        db.base().affectations.insert_one({"id": str(uuid.uuid4()), "personnel_id": a["personnel_id"], "date": jour, "creneau": a["creneau"], "type": "present", "note": "",
                                           "cree_par": u["login"], "cree_le": db.maintenant()})
        copiees += 1
    journaliser("planning_personnel_duplique", u, f"{src} → {dst} : {copiees}")
    return {"copiees": copiees, "ignorees": ignorees}
