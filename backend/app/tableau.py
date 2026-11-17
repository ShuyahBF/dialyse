"""Tableau de bord : indicateurs du jour et du mois (lectures indépendantes, agrégées en mémoire ; règle 7)."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Depends

from . import db, roles
from .auth import exiger_roles

routeur = APIRouter()


@routeur.get("/tableau")
def tableau(u: dict = Depends(exiger_roles(roles.LECTURE_RAPPORTS))):
    """Indicateurs : séances du jour par statut, occupation, patients par statut, incidents et séances sur 6 mois."""
    b = db.base()
    auj = date.today()
    jour = auj.isoformat()
    debut_mois = auj.replace(day=1)
    six_mois = (debut_mois - timedelta(days=150)).replace(day=1).isoformat()
    seances_jour = list(b.seances.find({"date": jour}, {"statut": 1, "creneau": 1, "poste_id": 1, "patient_id": 1}))
    par_statut = Counter(s["statut"] for s in seances_jour)
    postes = list(b.postes.find({}, {"statut": 1}))
    en_service = sum(1 for p in postes if p.get("statut") == "actif")
    capacite = en_service * 3                                         # 3 créneaux par jour et par poste
    actives = sum(1 for s in seances_jour if s["statut"] not in ("annulee", "absente"))
    pats = Counter(p.get("statut", "actif") for p in b.patients.find({}, {"statut": 1}))
    periode = list(b.seances.find({"date": {"$gte": six_mois}}, {"date": 1, "statut": 1, "incidents": 1}))
    par_mois: Counter = Counter()
    incidents_mois = 0
    for s in periode:
        if s["statut"] in ("terminee", "en_cours"):
            par_mois[s["date"][:7]] += 1
        if s["date"] >= debut_mois.isoformat():
            incidents_mois += len(s.get("incidents") or [])
    mois = []
    m = debut_mois
    for _ in range(6):
        mois.append(m.strftime("%Y-%m"))
        m = (m - timedelta(days=1)).replace(day=1)
    return {"date": jour, "seances_jour": {"total": len(seances_jour), "par_statut": dict(par_statut)},
            "postes": {"total": len(postes), "en_service": en_service}, "occupation_pct": round(100 * actives / capacite) if capacite else 0,
            "patients": dict(pats), "patients_actifs": pats.get("actif", 0), "incidents_mois": incidents_mois,
            "seances_par_mois": [{"mois": x, "nombre": par_mois.get(x, 0)} for x in reversed(mois)]}
