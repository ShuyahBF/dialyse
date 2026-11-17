"""
Accès à MongoDB. La base est ouverte à la première utilisation (Atlas) ou injectée par les tests (base en mémoire).
Collections : utilisateurs, parametres, journal, patients, postes, seances, historique.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .config import env

_base = None


def definir_base(base) -> None:
    """Utilisé par les tests pour fournir une base en mémoire."""
    global _base
    _base = base


def base():
    """Base de travail (ouverte une seule fois ; index créés à l'ouverture)."""
    global _base
    if _base is None:
        from pymongo import MongoClient
        uri = env("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI absent : à définir dans les variables d'environnement.")
        _base = MongoClient(uri, serverSelectionTimeoutMS=8000)[env("MONGODB_BASE", "dialyse")]
        creer_index(_base)
    return _base


def maintenant() -> str:
    """Date et heure UTC au format ISO (celle que l'on range en base)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def creer_index(b) -> None:
    """Index sur tout filtre fréquent (règle 7) : jamais de parcours complet d'une collection."""
    b.utilisateurs.create_index("login", unique=True)
    b.utilisateurs.create_index("id", unique=True)
    b.journal.create_index([("quand", -1)])
    b.patients.create_index("id", unique=True)
    b.patients.create_index("code", unique=True)
    b.patients.create_index([("nom_norm", 1), ("prenom_norm", 1)])
    b.patients.create_index("statut")
    b.postes.create_index("id", unique=True)
    b.seances.create_index("id", unique=True)
    b.seances.create_index([("date", 1), ("creneau", 1)])
    b.seances.create_index([("patient_id", 1), ("date", -1)])
    b.seances.create_index([("poste_id", 1), ("date", 1)])
    b.historique.create_index([("collection", 1), ("doc_id", 1), ("quand", -1)])
