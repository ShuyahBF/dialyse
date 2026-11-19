"""
Suivi ANONYMISÉ pour le directeur général et les médecins (application Android et écran « Suivi »).

Anonymisation décidée avec le propriétaire (17/11/2026) : on montre le code patient, l'âge, le sexe, le statut et les alertes ;
JAMAIS le nom, le prénom, le téléphone ni l'adresse. Le masquage est fait ICI, par le serveur (jamais par l'écran).

Alertes suivies : valeurs de bilan critiques, hypotension et autres alertes de séance, incidents, ruptures de stock, bilans en retard.
Les identifiants d'alerte sont STABLES : le téléphone ne notifie qu'une fois chaque alerte.

Notifications sur le téléphone : l'utilisateur crée un JETON DE LECTURE (aucun accès à autre chose que ce flux anonymisé). Seule son empreinte
est gardée ; il est annulé à la désactivation du compte, au retrait par l'utilisateur ou au changement de rôle hors des rôles autorisés.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException

from . import alertes as al
from . import bilans_ref as ref
from . import db, roles, validation
from .auth import exiger_roles, journaliser
from .stock import statut_stock

routeur = APIRouter()

# Rôles autorisés : directeur général, médecins et administration.
ROLES_SUIVI = {roles.DIRECTION, roles.MEDECIN, roles.ADMIN, roles.SUPER_ADMIN}
JOURS_SEANCES = 14          # les séances des 14 derniers jours alimentent les alertes
MAX_JETONS = 5              # téléphones par utilisateur


def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def construire(b=None) -> dict:
    """Alertes anonymisées + patients anonymisés (lectures EN BLOC : une requête par collection, règle 7)."""
    b = b or db.base()
    auj = date.today()
    depuis = (auj - timedelta(days=JOURS_SEANCES)).isoformat()
    patients = {p["id"]: p for p in b.patients.find({}, {"_id": 0, "id": 1, "code": 1, "sexe": 1, "date_naissance": 1, "statut": 1, "poids_sec": 1})}
    alertes: list[dict] = []

    def ajoute(id_, type_, gravite, code, message, date_):
        alertes.append({"id": id_, "type": type_, "gravite": gravite, "code": code, "message": message, "date": date_})

    # 1. Séances récentes : alertes cliniques et incidents (messages sans aucune identité)
    for s in b.seances.find({"date": {"$gte": depuis}, "statut": {"$in": ["en_cours", "terminee", "validee"]}}, {"_id": 0}):
        p = patients.get(s.get("patient_id"))
        if not p:
            continue
        for i, a in enumerate(al.alertes_seance(s, p.get("poids_sec"))):
            ajoute(f"s-{s['id']}-{i}", "seance", a["niveau"], p["code"], a["message"], s["date"])

    # 2. Bilans : dernier bilan de chaque patient actif (valeur critique, ou bilan en retard)
    actifs = [p for p in patients.values() if p.get("statut") == "actif"]
    derniers: dict = {}
    for bil in b.bilans.find({"patient_id": {"$in": [p["id"] for p in actifs]}}, {"_id": 0}).sort("date_prelevement", 1):
        derniers[bil["patient_id"]] = bil
    limite = (auj - timedelta(days=ref.JOURS_BILAN_MENSUEL)).isoformat()
    for p in actifs:
        d = derniers.get(p["id"])
        if not d or d["date_prelevement"] < limite:
            ajoute(f"br-{p['id']}-{d['date_prelevement'] if d else 'jamais'}", "bilan_retard", "attention", p["code"],
                   "Bilan biologique en retard" + (f" (dernier : {d['date_prelevement']})" if d else " (aucun bilan)"), auj.isoformat())
        if d:
            for i, a in enumerate(x for x in ref.analyser(d["resultats"])["alertes"] if x["niveau"] == "critique"):
                ajoute(f"bc-{d['id']}-{i}", "bilan_critique", "critique", p["code"], a["message"], d["date_prelevement"])

    # 3. Stock : ruptures d'articles suivis (aucun patient concerné)
    for a in b.articles.find({"actif": True}, {"_id": 0}):
        if statut_stock(a.get("stock", 0), a.get("seuil_alerte", 0)) == "rupture" and (a.get("seuil_alerte", 0) > 0 or a.get("par_seance", 0) > 0):
            ajoute(f"sr-{a['id']}", "stock_rupture", "critique", None, f"Rupture de stock : {a['nom']}", auj.isoformat())

    ordre = {"critique": 0, "attention": 1}
    alertes.sort(key=lambda x: x["date"], reverse=True)          # les plus récentes d'abord, puis les critiques avant les autres
    alertes.sort(key=lambda x: ordre.get(x["gravite"], 2))

    # Patients anonymisés : code, âge, sexe, statut, nombre d'alertes par patient
    par_code: dict = {}
    for a in alertes:
        if a["code"]:
            c = par_code.setdefault(a["code"], {"critiques": 0, "attention": 0})
            c["critiques" if a["gravite"] == "critique" else "attention"] += 1
    lignes = []
    for p in patients.values():
        c = par_code.get(p["code"], {"critiques": 0, "attention": 0})
        d = derniers.get(p["id"])
        lignes.append({"code": p["code"], "age": validation.age(p.get("date_naissance", "")), "sexe": p.get("sexe"), "statut": p.get("statut"),
                       "alertes_critiques": c["critiques"], "alertes_attention": c["attention"], "dernier_bilan": d["date_prelevement"] if d else ""})
    lignes.sort(key=lambda x: (-x["alertes_critiques"], -x["alertes_attention"], x["code"]))
    return {"alertes": alertes, "patients": lignes, "critiques": sum(1 for a in alertes if a["gravite"] == "critique"), "date": auj.isoformat()}


@routeur.get("/anonyme")
def suivi(u: dict = Depends(exiger_roles(ROLES_SUIVI))):
    """Alertes et patients ANONYMISÉS (écran « Suivi » et application Android). Consultation journalisée (aucune donnée dans le journal)."""
    journaliser("suivi_anonyme_lu", u)
    return construire()


@routeur.post("/anonyme/jeton")
def creer_jeton(corps: dict, u: dict = Depends(exiger_roles(ROLES_SUIVI))):
    """Crée le jeton de lecture des notifications d'UN téléphone (rendu une seule fois)."""
    b = db.base()
    jeton = secrets.token_urlsafe(32)
    anciens = list(b.jetons_alertes.find({"utilisateur_id": u["id"]}).sort("cree", 1))
    for a in anciens[: max(0, len(anciens) - (MAX_JETONS - 1))]:
        b.jetons_alertes.delete_one({"id": a["id"]})
    b.jetons_alertes.insert_one({"id": str(uuid.uuid4()), "utilisateur_id": u["id"], "centre_id": u.get("centre_id"), "empreinte": _empreinte(jeton),
                                 "appareil": str(corps.get("appareil", ""))[:60], "cree": db.maintenant()})
    journaliser("jeton_alertes_cree", u, str(corps.get("appareil", ""))[:60])
    return {"jeton": jeton}


@routeur.delete("/anonyme/jeton")
def retirer_jetons(u: dict = Depends(exiger_roles(ROLES_SUIVI))):
    """Annule tous les jetons de notification de l'utilisateur (tous ses téléphones)."""
    n = db.base().jetons_alertes.delete_many({"utilisateur_id": u["id"]}).deleted_count
    journaliser("jeton_alertes_retire", u)
    return {"retires": n}


@routeur.get("/anonyme/flux")
def flux(x_jeton_alertes: str = Header(default="")):
    """Flux des alertes ANONYMISÉES pour les notifications du téléphone. Authentifié par le seul jeton de lecture (aucun autre droit)."""
    b = db.base()
    fiche = b.jetons_alertes.find_one({"empreinte": _empreinte(x_jeton_alertes)}) if len(x_jeton_alertes) >= 20 else None
    ok = False
    if fiche:
        u = b.utilisateurs.find_one({"id": fiche["utilisateur_id"]})
        ok = bool(u and u.get("actif", True) and u.get("role") in ROLES_SUIVI and hmac.compare_digest(fiche["empreinte"], _empreinte(x_jeton_alertes)))
    if not ok:
        raise HTTPException(401, "Jeton de notification invalide")
    # Le flux ne porte QUE sur le centre du téléphone (celui du compte, ou celui choisi quand le jeton a été créé) : jamais un autre centre.
    centre = fiche.get("centre_id") or u.get("centre_id")
    if not centre:
        raise HTTPException(401, "Jeton de notification sans centre : recréez-le depuis l'application")
    db.fixer_centre(centre)
    r = construire(b)
    return {"alertes": r["alertes"], "critiques": r["critiques"]}
