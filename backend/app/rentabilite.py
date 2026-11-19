"""
RENTABILITÉ du centre : recettes (factures), coûts (personnel, maintenance, charges saisies) et indicateurs par mois : marge, coût et recette par séance, SEUIL DE RENTABILITÉ.

Montants en FCFA ENTIERS. Calcul par mois entier (`de` et `a` au format AAAA-MM) :
  recettes   = total des factures non annulées du mois (facturé) et encaissé (paiements enregistrés) ;
  coûts      = personnel (coût mensuel des salariés actifs) + maintenance (coût des interventions TERMINÉES du mois) + charges saisies du mois ;
  variables  = charges « consommables et médicaments » (varient avec le nombre de séances) ; fixes = tout le reste ;
  marge      = facturé − coûts ; coût par séance = coûts / séances réalisées ; seuil de rentabilité (séances) = coûts fixes / (recette moyenne − coût variable moyen par séance).
Réservé à l'administration et à la direction (données financières, agrégées : aucune identité de patient).
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from . import db, roles, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()

ACCES = {roles.ADMIN, roles.SUPER_ADMIN, roles.DIRECTION}
# catégorie → variable ? (True : varie avec le nombre de séances)
CATEGORIES = {"Consommables et médicaments": True, "Loyer": False, "Électricité (SONABEL)": False, "Eau": False, "Assurance": False, "Transport et divers": False, "Autre": False}
MAX_MOIS = 24


def _mois(corps_ou_valeur, libelle: str) -> str:
    v = str(corps_ou_valeur or "")
    try:
        a, m = v.split("-")
        if len(a) == 4 and 1 <= int(m) <= 12 and int(a) > 2000:
            return f"{int(a):04d}-{int(m):02d}"
    except ValueError:
        pass
    validation.erreur(f"{libelle} : mois au format AAAA-MM")


def _liste_mois(de: str, a: str) -> list[str]:
    ya, ma = int(de[:4]), int(de[5:])
    yb, mb = int(a[:4]), int(a[5:])
    n = (yb - ya) * 12 + (mb - ma) + 1
    if n < 1 or n > MAX_MOIS:
        validation.erreur(f"Période invalide (de 1 à {MAX_MOIS} mois)")
    return [f"{ya + (ma - 1 + i) // 12:04d}-{(ma - 1 + i) % 12 + 1:02d}" for i in range(n)]


def indicateurs(ligne: dict) -> dict:
    """Marge, coût et recette par séance, seuil de rentabilité d'un mois (ou d'un total). Fonction pure."""
    s = ligne["seances"]
    couts = ligne["couts"]
    marge = ligne["facture"] - couts
    recette_moy = ligne["facture"] / s if s else 0
    var_moy = ligne["couts_variables"] / s if s else 0
    unitaire = recette_moy - var_moy
    return {"marge": marge, "taux_marge_pct": round(100 * marge / ligne["facture"], 1) if ligne["facture"] else None, "cout_par_seance": round(couts / s) if s else None,
            "recette_par_seance": round(recette_moy) if s else None, "seuil_seances": round(ligne["couts_fixes"] / unitaire) if unitaire > 0 else None}


@routeur.get("/rentabilite/listes")
def listes(u: dict = Depends(exiger_roles(ACCES))):
    return {"categories": [{"valeur": k, "variable": v} for k, v in CATEGORIES.items()]}


@routeur.get("/rentabilite/charges")
def charges(mois: str = "", u: dict = Depends(exiger_roles(ACCES))):
    f = {"mois": _mois(mois, "Mois")} if mois else {}
    return [{k: v for k, v in c.items() if k not in ("_id", "centre_id")} for c in db.base().charges.find(f).sort([("mois", -1), ("categorie", 1)]).limit(500)]


@routeur.post("/rentabilite/charges")
def ajouter_charge(corps: dict, u: dict = Depends(exiger_roles(ACCES - {roles.DIRECTION}))):
    montant = validation.nombre(corps, "montant", "Montant (FCFA)", 1, 10_000_000_000)
    if montant is None:
        validation.erreur("Le montant est obligatoire")
    doc = {"id": str(uuid.uuid4()), "mois": _mois(corps.get("mois"), "Mois"), "categorie": validation.choix(corps, "categorie", "Catégorie", list(CATEGORIES), obligatoire=True),
           "montant": int(montant), "note": validation.texte(corps, "note", "Note", False, 200), "par": u["login"], "cree_le": db.maintenant()}
    db.base().charges.insert_one(doc)
    journaliser("charge_ajoutee", u, f"{doc['mois']} {doc['categorie']}")
    return {k: v for k, v in doc.items() if k != "_id"}


@routeur.delete("/rentabilite/charges/{id_}")
def supprimer_charge(id_: str, u: dict = Depends(exiger_roles(ACCES - {roles.DIRECTION}))):
    if not db.base().charges.find_one({"id": id_}):
        raise HTTPException(404, "Charge introuvable")
    db.base().charges.delete_one({"id": id_})
    journaliser("charge_supprimee", u, id_)
    return {"ok": True}


def calculer(de: str, a: str) -> dict:
    """Une ligne par mois + total. Quatre lectures en bloc pour toute la période (règle 7)."""
    mois = _liste_mois(de, a)
    debut, fin = mois[0] + "-01", mois[-1] + "-31"
    seances: dict = {}
    for s in db.base().seances.find({"date": {"$gte": debut, "$lte": fin}, "statut": {"$in": ["terminee", "en_cours"]}}, {"_id": 0, "date": 1}):
        seances[s["date"][:7]] = seances.get(s["date"][:7], 0) + 1
    facture: dict = {}
    encaisse: dict = {}
    for f in db.base().factures.find({"date": {"$gte": debut, "$lte": fin}, "annulee": {"$ne": True}}, {"_id": 0, "date": 1, "total": 1, "paiements": 1}):
        m = f["date"][:7]
        facture[m] = facture.get(m, 0) + int(f.get("total", 0))
        encaisse[m] = encaisse.get(m, 0) + sum(int(p.get("montant", 0)) for p in f.get("paiements", []))
    salaires = sum(int(p.get("cout_mensuel", 0)) for p in db.base().personnel.find({"actif": True}, {"cout_mensuel": 1}))
    maint: dict = {}
    for i in db.base().interventions.find({"statut": "terminee", "date_realisee": {"$gte": debut, "$lte": fin}}, {"_id": 0, "date_realisee": 1, "cout": 1}):
        maint[i["date_realisee"][:7]] = maint.get(i["date_realisee"][:7], 0) + int(i.get("cout", 0))
    saisies: dict = {}
    for c in db.base().charges.find({"mois": {"$gte": mois[0], "$lte": mois[-1]}}, {"_id": 0}):
        saisies.setdefault(c["mois"], {})[c["categorie"]] = saisies.get(c["mois"], {}).get(c["categorie"], 0) + int(c["montant"])
    lignes = []
    for m in mois:
        s = saisies.get(m, {})
        variables = sum(v for k, v in s.items() if CATEGORIES.get(k))
        autres = sum(v for k, v in s.items() if not CATEGORIES.get(k))
        fixes = salaires + maint.get(m, 0) + autres
        l = {"mois": m, "seances": seances.get(m, 0), "facture": facture.get(m, 0), "encaisse": encaisse.get(m, 0), "personnel": salaires, "maintenance": maint.get(m, 0), "charges": variables + autres,
             "couts_variables": variables, "couts_fixes": fixes, "couts": variables + fixes}
        lignes.append(l | indicateurs(l))
    total = {k: sum(l[k] for l in lignes) for k in ("seances", "facture", "encaisse", "personnel", "maintenance", "charges", "couts_variables", "couts_fixes", "couts")}
    return {"de": mois[0], "a": mois[-1], "mois": lignes, "total": total | indicateurs(total)}


@routeur.get("/rentabilite")
def rentabilite(de: str = "", a: str = "", u: dict = Depends(exiger_roles(ACCES))):
    """Rentabilité par mois ; par défaut les 6 derniers mois."""
    auj = date.today()
    fin = _mois(a, "À") if a else f"{auj.year:04d}-{auj.month:02d}"
    if de:
        debut = _mois(de, "De")
    else:                                                                       # 6 mois se terminant au mois `fin`
        n = int(fin[:4]) * 12 + int(fin[5:]) - 1 - 5
        debut = f"{n // 12:04d}-{n % 12 + 1:02d}"
    journaliser("rentabilite_consultee", u, f"{debut} → {fin}")
    return calculer(debut, fin)
