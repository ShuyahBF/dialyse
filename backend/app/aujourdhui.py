"""
Tableau de bord « AUJOURD'HUI » du centre : l'état des dialyses EN DIRECT, poste par poste, pour la journée en cours (heure UTC = heure du Burkina Faso).

Pour chaque poste : séance en cours (patient, début, fin prévue, temps restant, progression), prochaine séance, séances terminées. En haut : chiffres du jour,
retards à démarrer, séances qui se terminent bientôt, patients empêchés, réservations à traiter. Les alertes cliniques ne sont envoyées qu'au personnel médical
(`sea._public`) ; le secrétariat voit l'organisation sans détail médical. Lectures EN BLOC (règle 7) : une requête par collection.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from . import db, roles, seances as sea
from .auth import exiger_roles

routeur = APIRouter()

DUREE_PAR_DEFAUT_MIN = 240           # durée d'une séance sans prescription (4 h)
RETARD_MIN = 15                      # une séance planifiée non démarrée 15 min après son heure est « en retard »
FIN_PROCHE_MIN = 30                  # « se termine bientôt » : moins de 30 minutes restantes


def _heure(s: dict) -> str:
    return s.get("heure_prevue") or sea.CRENEAU_HEURE.get(s["creneau"], "07:00")


def _debut_prevu(jour: str, heure: str) -> datetime:
    h, m = heure.split(":")[:2]
    return datetime.fromisoformat(f"{jour}T{h}:{m}:00+00:00")


def calculer(maintenant: datetime, role: str) -> dict:
    """Photographie de la journée à l'instant `maintenant` (UTC) pour le centre courant."""
    jour = maintenant.date().isoformat()
    postes = list(db.base().postes.find({}, {"_id": 0}).sort("nom", 1))
    seances = list(db.base().seances.find({"date": jour}))
    pids = list({s["patient_id"] for s in seances})
    patients = {p["id"]: p for p in db.base().patients.find({"id": {"$in": pids}})} if pids else {}
    public = {s["id"]: p for s, p in zip(seances, sea._joindre(seances, role))}

    def duree(s: dict) -> int:
        d = ((s.get("parametres") or {}).get("duree_prevue_min")) or ((patients.get(s["patient_id"]) or {}).get("prescription") or {}).get("duree_min")
        return int(d or DUREE_PAR_DEFAUT_MIN)

    def carte(s: dict) -> dict:
        """Séance prête pour l'écran : patient, heure, et pour une séance en cours le temps restant et la progression."""
        d = public[s["id"]]
        c = {"id": s["id"], "statut": s["statut"], "statut_libelle": d["statut_libelle"], "patient": d["patient"], "heure": _heure(s), "creneau": s["creneau"],
             "confirmation_wa": s.get("confirmation_wa", ""), "alertes": d.get("alertes", []), "serologie_positive": d.get("serologie_positive", False)}
        if s["statut"] == "en_cours" and s.get("debut_a"):
            debut = datetime.fromisoformat(s["debut_a"])
            ecoule = max(0, int((maintenant - debut).total_seconds() // 60))
            total = duree(s)
            c.update({"debut": debut.strftime("%H:%M"), "duree_prevue_min": total, "ecoule_min": ecoule, "restant_min": max(0, total - ecoule),
                      "progression_pct": min(100, round(100 * ecoule / total)) if total else 0, "fin_prevue": (debut + timedelta(minutes=total)).strftime("%H:%M"), "depasse": ecoule > total})
        if s["statut"] == "terminee":
            c["fin"] = (s.get("fin_a") or "")[11:16]
        return c

    par_poste: dict = {p["id"]: [] for p in postes}
    for s in seances:
        par_poste.setdefault(s["poste_id"], []).append(s)
    cartes_postes = []
    for p in postes:
        liste = sorted(par_poste.get(p["id"], []), key=lambda s: (_heure(s), s["creneau"]))
        en_cours = next((s for s in liste if s["statut"] == "en_cours"), None)
        prochaine = next((s for s in liste if s["statut"] == "planifiee"), None)
        etat = "maintenance" if p.get("statut") == "maintenance" else "hors_service" if p.get("statut") == "hors_service" else "occupe" if en_cours else "libre"
        cartes_postes.append({"id": p["id"], "nom": p["nom"], "isolement": bool(p.get("isolement")), "etat": etat, "en_cours": carte(en_cours) if en_cours else None,
                              "prochaine": carte(prochaine) if prochaine else None, "terminees": sum(1 for s in liste if s["statut"] == "terminee"),
                              "maintenance_du_jour": p.get("prochaine_maintenance") == jour})

    planifiees = [s for s in seances if s["statut"] == "planifiee"]
    en_retard = [carte(s) | {"retard_min": int((maintenant - _debut_prevu(jour, _heure(s))).total_seconds() // 60)} for s in planifiees
                 if (maintenant - _debut_prevu(jour, _heure(s))).total_seconds() >= RETARD_MIN * 60]
    a_venir = sorted((carte(s) for s in planifiees if (maintenant - _debut_prevu(jour, _heure(s))).total_seconds() < RETARD_MIN * 60), key=lambda c: c["heure"])
    cours = [carte(s) for s in seances if s["statut"] == "en_cours"]
    fin_proche = sorted((c for c in cours if "restant_min" in c and c["restant_min"] <= FIN_PROCHE_MIN), key=lambda c: c["restant_min"])
    comptes = {k: sum(1 for s in seances if s["statut"] == k) for k in ("planifiee", "en_cours", "terminee", "absente", "annulee")}
    postes_actifs = [p for p in cartes_postes if p["etat"] in ("libre", "occupe")]
    res = {"date": jour, "heure": maintenant.strftime("%H:%M"), "comptes": comptes, "total_prevu": len(seances) - comptes["annulee"],
           "postes": cartes_postes, "postes_occupes": sum(1 for p in postes_actifs if p["etat"] == "occupe"), "postes_libres": sum(1 for p in postes_actifs if p["etat"] == "libre"),
           "postes_indisponibles": sum(1 for p in cartes_postes if p["etat"] in ("maintenance", "hors_service")), "en_retard": sorted(en_retard, key=lambda c: -c["retard_min"]),
           "a_venir": a_venir, "fin_proche": fin_proche, "depassees": [c for c in cours if c.get("depasse")],
           "empeches": [carte(s) for s in planifiees if s.get("confirmation_wa") == "empeche"],
           "reservations_attente": db.base().reservations.count_documents({"statut": "demandee"}),
           "demandes_wa": db.base().wa_demandes.count_documents({"statut": "nouvelle"}),
           "a_valider": db.base().seances.count_documents({"statut": "terminee", "date": jour, "validee_par": {"$exists": False}}) if roles.voit_medical(role) else None}
    return res


@routeur.get("/aujourdhui")
def aujourdhui(u: dict = Depends(exiger_roles(roles.LECTURE_SEANCE))):
    """Tableau de bord du jour (état des dialyses en direct), à relire toutes les 30 secondes par l'écran."""
    return calculer(datetime.now(timezone.utc), u["role"])


def nombre_en_retard(maintenant: datetime | None = None) -> int:
    """Nombre de séances planifiées non démarrées en retard (pastille du menu) : une seule lecture légère."""
    maintenant = maintenant or datetime.now(timezone.utc)
    jour = maintenant.date().isoformat()
    n = 0
    for s in db.base().seances.find({"date": jour, "statut": "planifiee"}, {"_id": 0, "creneau": 1, "heure_prevue": 1}):
        if (maintenant - _debut_prevu(jour, _heure(s))).total_seconds() >= RETARD_MIN * 60:
            n += 1
    return n
