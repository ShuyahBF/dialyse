"""
Accès à MongoDB. La base est ouverte à la première utilisation (Atlas) ou injectée par les tests (base en mémoire).
Collections : centres, contacts, wa_messages, wa_modeles, wa_demandes, wa_non_classes, retours_sawali, utilisateurs, parametres, journal, patients, postes, seances, bilans, articles, lots, mouvements, tarifs, organismes, factures, sauvegardes (+ morceaux), codes_acces, biometries, jetons_alertes, modeles_adhesion, passkeys, defis, historique.
"""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone

from .config import env

_base = None

# ---------------------------------------------------------------------------------------------------------------------------
# MULTI-CENTRES (modèle e-Kol : chaque centre a ses patients, ses séances, ses utilisateurs, etc.)
# Le centre « courant » est posé UNE FOIS par requête (auth.utilisateur_courant) dans cette variable de contexte. Toute collection
# listée dans COLLECTIONS_CENTRE est alors filtrée AUTOMATIQUEMENT sur ce centre (lecture, modification, suppression) et marquée
# `centre_id` à l'écriture : un écran ne peut donc pas « oublier » de filtrer. Sans centre courant, l'accès est REFUSÉ (jamais
# « tout »). Les traitements qui doivent voir tous les centres (sauvegardes, migration) passent par `brut()`.
# ---------------------------------------------------------------------------------------------------------------------------
COLLECTIONS_CENTRE = {"patients", "postes", "seances", "bilans", "articles", "lots", "mouvements", "tarifs", "organismes", "factures",
                      "modeles_adhesion", "historique", "parametres", "contacts", "wa_messages", "wa_modeles", "wa_demandes", "reservations", "liste_attente", "personnel", "affectations", "interventions", "controles_eau", "charges"}
centre_courant: ContextVar = ContextVar("centre_courant", default=None)


def fixer_centre(centre_id) -> None:
    """Définit le centre de travail de la requête en cours (None = aucun)."""
    centre_courant.set(centre_id)


def _centre_ou_erreur() -> str:
    """Centre courant, ou erreur 400 « choisissez un centre » (un compte du groupe doit en choisir un)."""
    c = centre_courant.get()
    if not c:
        from fastapi import HTTPException
        raise HTTPException(400, "Choisissez d'abord un centre de dialyse")
    return c


def _filtre(filtre) -> dict:
    """Filtre d'origine + condition centre (la condition du centre l'emporte toujours sur celle d'un appelant)."""
    return {**(filtre or {}), "centre_id": _centre_ou_erreur()}


class CollectionCentree:
    """Collection MongoDB limitée au centre courant. Seules les opérations sûres sont exposées (pas d'accès direct à la collection brute)."""

    def __init__(self, brute):
        self._c = brute

    def find(self, filtre=None, *a, **k):
        return self._c.find(_filtre(filtre), *a, **k)

    def find_one(self, filtre=None, *a, **k):
        return self._c.find_one(_filtre(filtre), *a, **k)

    def count_documents(self, filtre=None, *a, **k):
        return self._c.count_documents(_filtre(filtre), *a, **k)

    def distinct(self, cle, filtre=None, *a, **k):
        return self._c.distinct(cle, _filtre(filtre), *a, **k)

    def insert_one(self, doc, *a, **k):
        return self._c.insert_one({**doc, "centre_id": _centre_ou_erreur()}, *a, **k)

    def insert_many(self, docs, *a, **k):
        c = _centre_ou_erreur()
        return self._c.insert_many([{**d, "centre_id": c} for d in docs], *a, **k)

    def update_one(self, filtre, maj, *a, **k):
        return self._c.update_one(_filtre(filtre), maj, *a, **k)

    def update_many(self, filtre, maj, *a, **k):
        return self._c.update_many(_filtre(filtre), maj, *a, **k)

    def replace_one(self, filtre, doc, *a, **k):
        return self._c.replace_one(_filtre(filtre), {**doc, "centre_id": _centre_ou_erreur()}, *a, **k)

    def delete_one(self, filtre, *a, **k):
        return self._c.delete_one(_filtre(filtre), *a, **k)

    def delete_many(self, filtre, *a, **k):
        return self._c.delete_many(_filtre(filtre), *a, **k)

    def find_one_and_update(self, filtre, maj, *a, **k):
        return self._c.find_one_and_update(_filtre(filtre), maj, *a, **k)

    def find_one_and_delete(self, filtre, *a, **k):
        return self._c.find_one_and_delete(_filtre(filtre), *a, **k)

    def aggregate(self, pipeline, *a, **k):
        return self._c.aggregate([{"$match": {"centre_id": _centre_ou_erreur()}}, *pipeline], *a, **k)


class BaseCentree:
    """Base « vue du centre courant » : les collections de COLLECTIONS_CENTRE sont filtrées, les autres sont brutes."""

    def __init__(self, brute):
        self._b = brute

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return self[nom]

    def __getitem__(self, nom):
        return CollectionCentree(self._b[nom]) if nom in COLLECTIONS_CENTRE else self._b[nom]

    def command(self, *a, **k):
        return self._b.command(*a, **k)


def definir_base(base) -> None:
    """Utilisé par les tests pour fournir une base en mémoire."""
    global _base
    _base = base


def base():
    """Base de travail VUE DU CENTRE COURANT (collections par centre filtrées automatiquement). Pour tous les centres : `brut()`."""
    return BaseCentree(brut())


def brut():
    """Base complète, SANS filtre de centre (sauvegardes, migration, rapports de groupe). À n'utiliser que là, avec une raison claire."""
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
    # Anciens index UNIQUES d'avant le multi-centres (code patient, nom d'article, numéro de facture, id de modèle) : ils empêcheraient deux centres
    # d'avoir la même valeur. On les retire s'ils existent (déjà absents = sans effet) ; les index « par centre » ci-dessous les remplacent.
    for coll, nom in (("patients", "code_1"), ("articles", "nom_1"), ("factures", "numero_1"), ("modeles_adhesion", "id_1")):
        try:
            b[coll].drop_index(nom)
        except Exception:
            pass
    b.contacts.create_index([("centre_id", 1), ("numero", 1)], unique=True)           # un numéro = un contact DANS un centre
    b.contacts.create_index([("centre_id", 1), ("dernier_le", -1)])
    b.contacts.create_index("numero")                                               # réponses reçues : recherche du numéro dans tous les centres
    b.wa_messages.create_index([("centre_id", 1), ("contact_id", 1), ("cree_le", -1)])
    b.wa_messages.create_index("id", unique=True)
    b.wa_demandes.create_index([("centre_id", 1), ("statut", 1), ("cree_le", -1)])
    b.reservations.create_index([("centre_id", 1), ("date", 1), ("statut", 1)])
    b.reservations.create_index("id", unique=True)
    b.liste_attente.create_index([("centre_id", 1), ("statut", 1), ("priorite", 1)])
    b.personnel.create_index([("centre_id", 1), ("actif", 1)])
    b.affectations.create_index([("centre_id", 1), ("date", 1), ("creneau", 1)])
    b.affectations.create_index([("centre_id", 1), ("personnel_id", 1), ("date", 1)])
    b.interventions.create_index([("centre_id", 1), ("statut", 1), ("date_prevue", 1)])
    b.controles_eau.create_index([("centre_id", 1), ("test", 1), ("date", -1)])
    b.charges.create_index([("centre_id", 1), ("mois", 1)])
    b.centres.create_index("id", unique=True)
    b.centres.create_index("prefixe", unique=True)
    b.utilisateurs.create_index("centre_id")
    b.patients.create_index([("centre_id", 1), ("code", 1)], unique=True)        # code patient unique DANS un centre
    b.patients.create_index([("nom_norm", 1), ("prenom_norm", 1)])
    b.patients.create_index("statut")
    b.codes_acces.create_index("utilisateur_id")
    b.envois_acces.create_index([("utilisateur_id", 1), ("cree", -1)])
    b.biometries.create_index([("utilisateur_id", 1), ("appareil_id", 1)])
    b.jetons_alertes.create_index("empreinte", unique=True)       # jetons de notification (empreinte SHA-256 seulement)
    b.jetons_alertes.create_index("utilisateur_id")
    b.modeles_adhesion.create_index([("centre_id", 1), ("id", 1)], unique=True)   # modèles de dossier d'adhésion : le modèle « defaut » existe dans chaque centre
    b.passkeys.create_index("credential_id", unique=True)
    b.defis.create_index("id", unique=True)
    b.sauvegardes.create_index("id", unique=True)
    b.sauvegardes.create_index([("origine", 1), ("cree_le", -1)])
    b.sauvegardes_morceaux.create_index([("sauvegarde_id", 1), ("n", 1)])
    b.articles.create_index("id", unique=True)
    b.articles.create_index([("centre_id", 1), ("nom", 1)], unique=True)           # nom d'article unique DANS un centre
    b.lots.create_index([("article_id", 1), ("numero", 1)])
    b.mouvements.create_index([("article_id", 1), ("quand", -1)])
    b.mouvements.create_index("lots.numero")
    b.factures.create_index("id", unique=True)
    b.factures.create_index([("centre_id", 1), ("numero", 1)], unique=True)        # numéro de facture unique DANS un centre
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
