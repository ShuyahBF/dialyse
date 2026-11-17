"""Historique des modifications d'une fiche : qui, quand, quels CHAMPS (jamais les valeurs, pour ne pas dupliquer de données médicales)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from . import db, roles
from .auth import exiger_roles, journaliser

routeur = APIRouter()
COLLECTIONS = ("patients", "postes", "seances", "bilans")
TECHNIQUES = {"updated_at", "maj_par", "id", "created_at", "cree_par", "nom_norm", "prenom_norm", "code"}


def noter(collection: str, doc_id: str, acteur: dict, champs: list[str], action: str = "modification") -> None:
    """Range une ligne d'historique (noms des champs modifiés, sans valeurs)."""
    champs = [c for c in champs if c not in TECHNIQUES]
    if action == "modification" and not champs:
        return
    db.base().historique.insert_one({"collection": collection, "doc_id": doc_id, "quand": db.maintenant(), "par": acteur.get("login"),
                                     "role": acteur.get("role"), "action": action, "champs": sorted(champs)})


def champs_modifies(avant: dict, apres: dict) -> list[str]:
    """Noms des champs dont la valeur a changé entre deux versions d'un document."""
    return [k for k in apres if avant.get(k) != apres.get(k)]


@routeur.get("/historique/{collection}/{doc_id}")
def historique(collection: str, doc_id: str, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Les 200 dernières lignes de l'historique du document (consultation journalisée)."""
    if collection not in COLLECTIONS:
        raise HTTPException(400, "Collection inconnue")
    doc = db.base()[collection].find_one({"id": doc_id})
    if not doc:
        raise HTTPException(404, "Fiche introuvable")
    lignes = list(db.base().historique.find({"collection": collection, "doc_id": doc_id}, {"_id": 0}).sort("quand", -1).limit(200))
    journaliser("historique_lu", u, f"{collection}/{doc_id}")
    return {"cree_par": doc.get("cree_par", ""), "cree_le": doc.get("created_at", ""), "maj_par": doc.get("maj_par", ""),
            "maj_le": doc.get("updated_at", ""), "lignes": lignes}
