"""
Bilans biologiques des patients : saisie, correction, évolution d'un paramètre, bilans en retard.
Données médicales : visibles du personnel soignant et de l'administration seulement (jamais le secrétariat).
Chaque bilan est rattaché à un patient ; l'interprétation (statuts, URR, alertes) est calculée à la lecture, pas stockée.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from . import bilans_ref as ref, db, historique, roles, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()


def _public(b: dict) -> dict:
    d = {k: v for k, v in b.items() if k != "_id"}
    d["analyse"] = ref.analyser(b.get("resultats", {}))
    return d


def _resultats(corps: dict) -> dict:
    """Résultats validés : seuls les paramètres du catalogue, en nombres plausibles (positifs) ; au moins un résultat."""
    brut = corps.get("resultats") or {}
    inconnus = [k for k in brut if k not in ref.PARAMETRES]
    if inconnus:
        validation.erreur("Paramètre inconnu : " + ", ".join(sorted(inconnus)))
    res = {}
    for cle, v in brut.items():
        n = validation.nombre({cle: v}, cle, ref.PARAMETRES[cle]["libelle"], 0, 100000)
        if n is not None:
            res[cle] = n
    if not res:
        validation.erreur("Saisissez au moins un résultat")
    return res


@routeur.get("/bilans/parametres")
def parametres(u: dict = Depends(exiger_roles(roles.VOIT_MEDICAL))):
    """Catalogue des paramètres (libellé, unité, cible) et types de bilan : alimente le formulaire et les couleurs."""
    return {"parametres": [{"cle": k, "libelle": p["libelle"], "unite": p["unite"], "mini": p["cible"][0], "maxi": p["cible"][1]} for k, p in ref.PARAMETRES.items()],
            "types": ref.TYPES_BILAN, "urr_cible": ref.URR_CIBLE}


@routeur.get("/patients/{pid}/bilans")
def lister(pid: str, u: dict = Depends(exiger_roles(roles.VOIT_MEDICAL))):
    """Bilans d'un patient, du plus récent au plus ancien, avec interprétation (consultation journalisée)."""
    p = db.base().patients.find_one({"id": pid}, {"code": 1})
    if not p:
        raise HTTPException(404, "Patient introuvable")
    lignes = list(db.base().bilans.find({"patient_id": pid}, {"_id": 0}).sort("date_prelevement", -1).limit(200))
    journaliser("bilans_lus", u, p["code"])
    return [_public(b) for b in lignes]


@routeur.post("/patients/{pid}/bilans")
def creer(pid: str, corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_MEDICAL))):
    """Enregistre un bilan (date de prélèvement non future, type, résultats). Renvoie le bilan interprété."""
    p = db.base().patients.find_one({"id": pid}, {"code": 1})
    if not p:
        raise HTTPException(404, "Patient introuvable")
    doc = {"id": str(uuid.uuid4()), "patient_id": pid, "date_prelevement": validation.date_iso(corps, "date_prelevement", "Date de prélèvement", True, futur_ok=False),
           "type": validation.choix(corps, "type", "Type de bilan", ref.TYPES_BILAN, defaut="Mensuel"), "resultats": _resultats(corps),
           "commentaire": validation.texte(corps, "commentaire", "Commentaire", False, 500),
           "created_at": db.maintenant(), "cree_par": u["login"], "updated_at": db.maintenant(), "maj_par": u["login"]}
    db.base().bilans.insert_one(doc)
    historique.noter("bilans", doc["id"], u, [], "creation")
    journaliser("bilan_cree", u, p["code"])
    return _public(doc)


@routeur.put("/bilans/{bid}")
def corriger(bid: str, corps: dict, u: dict = Depends(exiger_roles(roles.PRESCRIPTION))):
    """Correction d'un bilan par le médecin (ou l'administration) : date, type, résultats, commentaire. Historique gardé."""
    b = db.base().bilans.find_one({"id": bid})
    if not b:
        raise HTTPException(404, "Bilan introuvable")
    maj: dict = {}
    if "date_prelevement" in corps:
        maj["date_prelevement"] = validation.date_iso(corps, "date_prelevement", "Date de prélèvement", True, futur_ok=False)
    if "type" in corps:
        maj["type"] = validation.choix(corps, "type", "Type de bilan", ref.TYPES_BILAN, obligatoire=True)
    if "resultats" in corps:
        maj["resultats"] = _resultats(corps)
    if "commentaire" in corps:
        maj["commentaire"] = validation.texte(corps, "commentaire", "Commentaire", False, 500)
    ch = historique.champs_modifies(b, maj)
    if ch:
        maj.update({"updated_at": db.maintenant(), "maj_par": u["login"]})
        db.base().bilans.update_one({"id": bid}, {"$set": maj})
        historique.noter("bilans", bid, u, ch)
        journaliser("bilan_corrige", u, bid)
    return _public(db.base().bilans.find_one({"id": bid}))


@routeur.delete("/bilans/{bid}")
def supprimer(bid: str, u: dict = Depends(exiger_roles(roles.SUPPRESSION))):
    """Suppression d'un bilan saisi par erreur : administration seulement, journalisée."""
    if not db.base().bilans.find_one({"id": bid}):
        raise HTTPException(404, "Bilan introuvable")
    db.base().bilans.delete_one({"id": bid})
    journaliser("bilan_supprime", u, bid)
    return {"ok": True}


@routeur.get("/patients/{pid}/bilans/evolution/{cle}")
def evolution(pid: str, cle: str, u: dict = Depends(exiger_roles(roles.VOIT_MEDICAL))):
    """Série chronologique d'un paramètre (ou « urr ») pour tracer la courbe : [{date, valeur, statut}]."""
    if cle != "urr" and cle not in ref.PARAMETRES:
        raise HTTPException(404, "Paramètre inconnu")
    serie = []
    for b in db.base().bilans.find({"patient_id": pid}, {"_id": 0}).sort("date_prelevement", 1):
        if cle == "urr":
            v = ref.urr(b["resultats"].get("uree_pre"), b["resultats"].get("uree_post"))
            if v is not None:
                serie.append({"date": b["date_prelevement"], "valeur": v, "statut": "normal" if v >= ref.URR_CIBLE else "bas"})
        elif cle in b["resultats"]:
            serie.append({"date": b["date_prelevement"], "valeur": b["resultats"][cle], "statut": ref.interpreter(cle, b["resultats"][cle])})
    return serie


@routeur.get("/bilans/suivi")
def suivi(u: dict = Depends(exiger_roles(roles.LECTURE_STATS))):
    """
    Tableau de suivi (lectures en bloc) : patients actifs dont le dernier bilan a plus de 35 jours (ou sans bilan),
    et patients dont le dernier bilan contient une valeur critique.
    """
    b = db.base()
    actifs = list(b.patients.find({"statut": "actif"}, {"_id": 0, "id": 1, "code": 1, "nom": 1, "prenom": 1}))
    ids = [p["id"] for p in actifs]
    derniers: dict = {}
    for bil in b.bilans.find({"patient_id": {"$in": ids}}, {"_id": 0}).sort("date_prelevement", 1):
        derniers[bil["patient_id"]] = bil                      # le dernier écrase les précédents (ordre chronologique)
    limite = (date.today() - timedelta(days=ref.JOURS_BILAN_MENSUEL)).isoformat()
    en_retard, critiques = [], []
    for p in actifs:
        d = derniers.get(p["id"])
        ident = {"id": p["id"], "code": p["code"], "nom": p["nom"], "prenom": p["prenom"]}
        if not d or d["date_prelevement"] < limite:
            en_retard.append({**ident, "dernier_bilan": d["date_prelevement"] if d else ""})
        if d:
            crit = [a["message"] for a in ref.analyser(d["resultats"])["alertes"] if a["niveau"] == "critique"]
            if crit:
                critiques.append({**ident, "date": d["date_prelevement"], "messages": crit})
    return {"en_retard": sorted(en_retard, key=lambda x: x["dernier_bilan"]), "critiques": critiques, "jours_limite": ref.JOURS_BILAN_MENSUEL}
