"""
Accès à MongoDB. La base est ouverte à la première utilisation (Atlas) ou injectée par les tests (base en mémoire).
Collections : utilisateurs, parametres, journal, patients, postes, seances, bilans, articles, lots, mouvements, tarifs, organismes, factures, sauvegardes (+ morceaux), codes_acces, biometries, jetons_alertes, passkeys, defis, historique.
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
    b.codes_acces.create_index("utilisateur_id")
    b.envois_acces.create_index([("utilisateur_id", 1), ("cree", -1)])
    b.biometries.create_index([("utilisateur_id", 1), ("appareil_id", 1)])
    b.jetons_alertes.create_index("empreinte", unique=True)       # jetons de notification (empreinte SHA-256 seulement)
    b.jetons_alertes.create_index("utilisateur_id")
    b.passkeys.create_index("credential_id", unique=True)
    b.defis.create_index("id", unique=True)
    b.sauvegardes.create_index("id", unique=True)
    b.sauvegardes.create_index([("origine", 1), ("cree_le", -1)])
    b.sauvegardes_morceaux.create_index([("sauvegarde_id", 1), ("n", 1)])
    b.articles.create_index("id", unique=True)
    b.articles.create_index("nom", unique=True)
    b.lots.create_index([("article_id", 1), ("numero", 1)])
    b.mouvements.create_index([("article_id", 1), ("quand", -1)])
    b.mouvements.create_index("lots.numero")
    b.factures.create_index("id", unique=True)
    b.factures.create_index("numero", unique=True)
    b.factures.create_index([("date", -1)])
    b.factures.create_index("seance_id")
    b.factures.create_index("patient_id")
    b.tarifs.create_index("id", unique=True)
    b.organismes.create_index("id", unique=True)
    b.bilans.create_index("id", unique=True)
    b.bilans.create_index([("patient_id", 1), ("date_prelevement", -1)])
    b.postes.create_index("id", unique=True)
    b.seances.create_index("id", unique=True)
    b.seances.create_index([("date", 1), ("creneau", 1)])
    b.seances.create_index([("patient_id", 1), ("date", -1)])
    b.seances.create_index([("poste_id", 1), ("date", 1)])
    b.historique.create_index([("collection", 1), ("doc_id", 1), ("quand", -1)])
