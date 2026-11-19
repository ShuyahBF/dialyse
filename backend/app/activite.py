"""
Espace d'ACTIVITÉ du centre : réservations de séances, calendrier interactif (mois et jour), liste d'attente.

- Une RÉSERVATION est une demande de place (patient, date, créneau, motif) : demandée → confirmée (le serveur crée alors la séance planifiée sur le poste choisi, avec
  tous les contrôles du planning) → ou refusée / annulée. Elle peut venir de l'écran (secrétariat) ou d'une demande reçue par WhatsApp. Le patient est prévenu par WhatsApp
  (confirmation, refus) quand c'est possible, sans aucune donnée médicale.
- Le CALENDRIER donne, jour par jour, les séances par état, les réservations en attente, le taux d'occupation et les maintenances de postes ; le détail d'un jour
  est une grille postes × créneaux. Lectures EN BLOC (règle 7), jamais une requête par jour.
- La LISTE D'ATTENTE garde les personnes qui attendent une place en dialyse, avec une priorité.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from . import db, patients as pat, roles, seances as sea, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()

MOTIFS_RESERVATION = ["Séance supplémentaire", "Rattrapage d'une séance manquée", "Nouvelle admission", "Patient de passage", "Changement de créneau", "Autre"]
STATUTS_RESERVATION = ["demandee", "confirmee", "refusee", "annulee"]
LIBELLE_RESERVATION = {"demandee": "Demandée", "confirmee": "Confirmée", "refusee": "Refusée", "annulee": "Annulée"}
PRIORITES = ["urgente", "normale", "basse"]
STATUTS_ATTENTE = ["en_attente", "admis", "retire"]
MAX_JOURS_CALENDRIER = 62


def _public(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("_id", "centre_id")}


def _reservation(id_: str) -> dict:
    r = db.base().reservations.find_one({"id": id_})
    if not r:
        raise HTTPException(404, "Réservation introuvable")
    return r


def _fr(jour: str) -> str:
    return f"{jour[8:]}/{jour[5:7]}/{jour[:4]}"


# ---------- réservations ----------

@routeur.get("/reservations/listes")
def listes_reservation(u: dict = Depends(exiger_roles(roles.PLANNING))):
    return {"motifs": MOTIFS_RESERVATION, "creneaux": pat.CRENEAUX, "statuts": [{"valeur": s, "libelle": LIBELLE_RESERVATION[s]} for s in STATUTS_RESERVATION], "heures_creneaux": sea.CRENEAU_HEURE}


@routeur.get("/reservations")
def lister_reservations(du: str = "", au: str = "", statut: str = "", u: dict = Depends(exiger_roles(roles.PLANNING))):
    """Réservations d'une période (date de la séance demandée) et/ou d'un état ; les plus proches d'abord."""
    f: dict = {}
    if du or au:
        f["date"] = {}
        if du:
            f["date"]["$gte"] = validation.date_iso({"d": du}, "d", "Du")
        if au:
            f["date"]["$lte"] = validation.date_iso({"d": au}, "d", "Au")
    if statut:
        f["statut"] = statut
    return [_public(r) | {"statut_libelle": LIBELLE_RESERVATION.get(r["statut"], r["statut"])} for r in db.base().reservations.find(f).sort([("date", 1), ("creneau", 1)]).limit(500)]


@routeur.post("/reservations")
def creer_reservation(corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    """Nouvelle demande de place. `poste_id` + `confirmer` vrai : confirmée tout de suite (séance créée). `demande_id` : demande WhatsApp d'origine, marquée traitée."""
    jour = validation.date_iso(corps, "date", "Date", True)
    if jour < date.today().isoformat():
        validation.erreur("La date de la réservation ne peut pas être passée")
    creneau = validation.choix(corps, "creneau", "Créneau", pat.CRENEAUX, obligatoire=True)
    p = db.base().patients.find_one({"id": str(corps.get("patient_id") or "")})
    if not p:
        raise HTTPException(404, "Patient introuvable")
    doc = {"id": str(uuid.uuid4()), "patient_id": p["id"], "patient_nom": f"{p['nom']} {p['prenom']}", "patient_code": p["code"], "date": jour, "creneau": creneau,
           "motif": validation.choix(corps, "motif", "Motif", MOTIFS_RESERVATION, defaut="Autre"), "note": validation.texte(corps, "note", "Note", False, 300), "statut": "demandee",
           "source": "whatsapp" if corps.get("demande_id") else "manuel", "demande_id": str(corps.get("demande_id") or ""), "seance_id": "", "cree_par": u["login"], "cree_le": db.maintenant()}
    db.base().reservations.insert_one(doc)
    if doc["demande_id"]:
        db.base().wa_demandes.update_one({"id": doc["demande_id"]}, {"$set": {"statut": "traitee", "traite_par": u["login"], "traite_le": db.maintenant(), "note": "Convertie en réservation"}})
    journaliser("reservation_creee", u, f"{doc['id']} {jour} {creneau}")
    if corps.get("confirmer") and corps.get("poste_id"):
        return _confirmer(doc, str(corps["poste_id"]), u)
    return _public(doc)


def _confirmer(r: dict, poste_id: str, u: dict) -> dict:
    """Confirme : crée la séance planifiée (contrôles du planning : patient actif, poste en service et libre, patient libre) puis prévient le patient."""
    if r["statut"] != "demandee":
        raise HTTPException(409, "Cette réservation n'est plus en attente")
    seance, prevenir = sea._creer({"patient_id": r["patient_id"], "date": r["date"], "creneau": r["creneau"], "poste_id": poste_id}, u, source="reservation")
    db.base().reservations.update_one({"id": r["id"]}, {"$set": {"statut": "confirmee", "seance_id": seance["id"], "poste_id": poste_id, "traite_par": u["login"], "traite_le": db.maintenant()}})
    journaliser("reservation_confirmee", u, r["id"])
    from .messagerie import notifier
    notifier("reservation_confirmee", r["patient_id"], {"date": r["date"], "creneau": r["creneau"], "heure": sea.CRENEAU_HEURE.get(r["creneau"], "")})
    return _public(db.base().reservations.find_one({"id": r["id"]})) | {"alertes_planification": prevenir}


@routeur.post("/reservations/{id_}/confirmer")
def confirmer_reservation(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    return _confirmer(_reservation(id_), str(corps.get("poste_id") or ""), u)


@routeur.post("/reservations/{id_}/refuser")
def refuser_reservation(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    r = _reservation(id_)
    if r["statut"] != "demandee":
        raise HTTPException(409, "Cette réservation n'est plus en attente")
    motif = validation.texte(corps, "motif", "Motif du refus", True, 200)
    db.base().reservations.update_one({"id": id_}, {"$set": {"statut": "refusee", "motif_refus": motif, "traite_par": u["login"], "traite_le": db.maintenant()}})
    journaliser("reservation_refusee", u, id_)
    from .messagerie import notifier
    notifier("reservation_refusee", r["patient_id"], {"date": r["date"], "creneau": r["creneau"]})
    return _public(db.base().reservations.find_one({"id": id_}))


@routeur.post("/reservations/{id_}/annuler")
def annuler_reservation(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    """Annule une réservation ; si elle avait créé une séance encore planifiée, la séance est annulée aussi."""
    r = _reservation(id_)
    if r["statut"] in ("refusee", "annulee"):
        raise HTTPException(409, "Cette réservation est déjà close")
    if r.get("seance_id"):
        s = db.base().seances.find_one({"id": r["seance_id"]})
        if s and s["statut"] != "planifiee":
            raise HTTPException(409, "La séance a déjà commencé : elle ne peut plus être annulée ici")
        if s:
            db.base().seances.update_one({"id": s["id"]}, {"$set": {"statut": "annulee", "motif": "Réservation annulée", "updated_at": db.maintenant()}})
    db.base().reservations.update_one({"id": id_}, {"$set": {"statut": "annulee", "traite_par": u["login"], "traite_le": db.maintenant(), "note": validation.texte(corps, "note", "Note", False, 300)}})
    journaliser("reservation_annulee", u, id_)
    from .messagerie import notifier
    notifier("reservation_annulee", r["patient_id"], {"date": r["date"], "creneau": r["creneau"]})
    return _public(db.base().reservations.find_one({"id": id_}))


# ---------- calendrier ----------

def _bornes(du: str, au: str) -> tuple[str, str]:
    du, au = validation.date_iso({"d": du}, "d", "Du", True), validation.date_iso({"d": au}, "d", "Au", True)
    if au < du or (date.fromisoformat(au) - date.fromisoformat(du)).days >= MAX_JOURS_CALENDRIER:
        validation.erreur(f"Période invalide (de 1 à {MAX_JOURS_CALENDRIER} jours)")
    return du, au


@routeur.get("/calendrier")
def calendrier(du: str, au: str, u: dict = Depends(exiger_roles(roles.LECTURE_SEANCE))):
    """
    Une ligne par jour : séances par état, réservations en attente / confirmées, capacité (postes en service × créneaux), taux d'occupation, maintenances de postes.
    Trois lectures en bloc pour toute la période (règle 7).
    """
    du, au = _bornes(du, au)
    postes = list(db.base().postes.find({}, {"_id": 0, "id": 1, "nom": 1, "statut": 1, "prochaine_maintenance": 1}))
    capacite = sum(1 for p in postes if p.get("statut") == "actif") * len(pat.CRENEAUX)
    par_jour: dict = defaultdict(lambda: defaultdict(int))
    for s in db.base().seances.find({"date": {"$gte": du, "$lte": au}}, {"_id": 0, "date": 1, "statut": 1}):
        par_jour[s["date"]][s["statut"]] += 1
    for r in db.base().reservations.find({"date": {"$gte": du, "$lte": au}, "statut": {"$in": ["demandee", "confirmee"]}}, {"_id": 0, "date": 1, "statut": 1}):
        par_jour[r["date"]]["res_" + r["statut"]] += 1
    maintenances = defaultdict(list)
    for p in postes:
        if p.get("prochaine_maintenance") and du <= p["prochaine_maintenance"] <= au:
            maintenances[p["prochaine_maintenance"]].append(p["nom"])
    jours, d = [], date.fromisoformat(du)
    while d <= date.fromisoformat(au):
        c = par_jour.get(d.isoformat(), {})
        occupees = c.get("planifiee", 0) + c.get("en_cours", 0) + c.get("terminee", 0)
        jours.append({"date": d.isoformat(), "planifiee": c.get("planifiee", 0), "en_cours": c.get("en_cours", 0), "terminee": c.get("terminee", 0), "absente": c.get("absente", 0),
                      "annulee": c.get("annulee", 0), "reservations_attente": c.get("res_demandee", 0), "reservations_confirmees": c.get("res_confirmee", 0),
                      "occupation_pct": round(100 * occupees / capacite) if capacite else 0, "maintenances": maintenances.get(d.isoformat(), [])})
        d += timedelta(days=1)
    return {"du": du, "au": au, "capacite": capacite, "jours": jours}


@routeur.get("/calendrier/jour")
def calendrier_jour(date_: str = Query(..., alias="date"), u: dict = Depends(exiger_roles(roles.LECTURE_SEANCE))):
    """Détail d'un jour : grille postes × créneaux (séance ou case libre), réservations du jour, maintenances. Le secrétariat ne reçoit aucun détail médical (`sea._public`)."""
    jour = validation.date_iso({"d": date_}, "d", "Date", True)
    postes = list(db.base().postes.find({}, {"_id": 0}).sort("nom", 1))
    seances = sea._joindre(list(db.base().seances.find({"date": jour, "statut": {"$nin": ["annulee"]}})), u["role"])
    par_case = {(s["poste_id"], s["creneau"]): s for s in seances}
    cellules = [{"poste_id": p["id"], "creneau": c, "seance": ({k: s.get(k) for k in ("id", "statut", "statut_libelle", "patient", "debut_a", "fin_a", "confirmation_wa", "rappel_wa_le", "alertes", "serologie_positive")}
                                                              if (s := par_case.get((p["id"], c))) else None)} for p in postes for c in pat.CRENEAUX]
    reservations = [_public(r) | {"statut_libelle": LIBELLE_RESERVATION[r["statut"]]} for r in db.base().reservations.find({"date": jour, "statut": {"$in": ["demandee", "confirmee"]}}).sort("creneau", 1)]
    return {"date": jour, "creneaux": pat.CRENEAUX, "heures_creneaux": sea.CRENEAU_HEURE,
            "postes": [{"id": p["id"], "nom": p["nom"], "statut": p.get("statut"), "isolement": bool(p.get("isolement")), "prochaine_maintenance": p.get("prochaine_maintenance", "")} for p in postes],
            "cellules": cellules, "reservations": reservations, "maintenances": [p["nom"] for p in postes if p.get("prochaine_maintenance") == jour]}


# ---------- liste d'attente ----------

@routeur.get("/attente")
def lister_attente(statut: str = "en_attente", u: dict = Depends(exiger_roles(roles.PLANNING))):
    """Personnes en attente d'une place, les plus urgentes puis les plus anciennes d'abord."""
    ordre = {p: i for i, p in enumerate(PRIORITES)}
    lignes = [_public(a) for a in db.base().liste_attente.find({"statut": statut} if statut else {})]
    lignes.sort(key=lambda a: (ordre.get(a["priorite"], 9), a["cree_le"]))
    return lignes


@routeur.post("/attente")
def ajouter_attente(corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    doc = {"id": str(uuid.uuid4()), "nom": validation.texte(corps, "nom", "Nom", True, 80).upper(), "prenom": validation.texte(corps, "prenom", "Prénom", True, 80),
           "telephone": validation.texte(corps, "telephone", "Téléphone", False, 30), "motif": validation.texte(corps, "motif", "Motif", False, 200),
           "priorite": validation.choix(corps, "priorite", "Priorité", PRIORITES, defaut="normale"), "statut": "en_attente", "cree_par": u["login"], "cree_le": db.maintenant()}
    db.base().liste_attente.insert_one(doc)
    journaliser("attente_ajout", u, doc["id"])
    return _public(doc)


@routeur.put("/attente/{id_}")
def modifier_attente(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    a = db.base().liste_attente.find_one({"id": id_})
    if not a:
        raise HTTPException(404, "Personne introuvable")
    maj: dict = {}
    if "priorite" in corps:
        maj["priorite"] = validation.choix(corps, "priorite", "Priorité", PRIORITES, obligatoire=True)
    if "statut" in corps:
        maj["statut"] = validation.choix(corps, "statut", "État", STATUTS_ATTENTE, obligatoire=True)
    for cle, lib, long_ in (("motif", "Motif", 200), ("telephone", "Téléphone", 30)):
        if cle in corps:
            maj[cle] = validation.texte(corps, cle, lib, False, long_)
    if maj:
        db.base().liste_attente.update_one({"id": id_}, {"$set": maj})
    return _public(db.base().liste_attente.find_one({"id": id_}))
