"""
Centres de dialyse (multi-centres, sur le modèle d'e-Kol : « une école = un centre »).

Chaque centre possède SES patients, postes, séances, bilans, stocks, factures, modèles de dossier et SES utilisateurs. Le compte d'un centre ne voit
jamais un autre centre (le serveur filtre, voir `db.CollectionCentree`). Le super administrateur crée les centres ; lui et le directeur général (comptes
« du groupe », sans centre) choisissent le centre où ils travaillent.
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException

from . import db, roles, validation
from .auth import exiger_roles, journaliser, utilisateur_courant

routeur = APIRouter()

CENTRE_INITIAL = "centre-initial"          # identifiant du centre créé automatiquement pour reprendre les données d'avant le multi-centres
PREFIXE_INITIAL = "DIAL"                   # préfixe des codes patients existants (DIAL-000001) : conservé pour le centre initial


def _public(c: dict) -> dict:
    """Fiche d'un centre telle qu'elle est montrée à l'écran."""
    return {"id": c["id"], "nom": c["nom"], "prefixe": c["prefixe"], "ville": c.get("ville", ""), "telephone": c.get("telephone", ""),
            "actif": c.get("actif", True), "cree_le": c.get("cree_le", "")}


def amorcer_centre_initial() -> None:
    """
    Migration idempotente vers le multi-centres : s'il n'existe aucun centre, crée « Centre principal » et y rattache TOUTES les données
    existantes (patients, séances… et comptes, sauf les comptes du groupe). Relancée à chaque démarrage sans effet une fois faite.
    """
    b = db.brut()
    orphelins = any(b[n].count_documents({"centre_id": {"$exists": False}}, limit=1) for n in db.COLLECTIONS_CENTRE | {"journal"}) \
        or b.utilisateurs.count_documents({"centre_id": {"$exists": False}, "role": {"$nin": list(roles.ROLES_GROUPE)}}, limit=1)
    if not b.centres.find_one({"id": CENTRE_INITIAL}) and (b.centres.count_documents({}) == 0 or orphelins):
        b.centres.insert_one({"id": CENTRE_INITIAL, "nom": "Centre principal", "prefixe": PREFIXE_INITIAL, "ville": "", "telephone": "",
                              "actif": True, "cree_le": db.maintenant()})
    ancien = b.centres.find_one({"id": CENTRE_INITIAL})
    if not ancien:
        return                                                  # centres déjà créés à la main : rien à rattacher d'office
    for nom in db.COLLECTIONS_CENTRE | {"journal"}:
        b[nom].update_many({"centre_id": {"$exists": False}}, {"$set": {"centre_id": CENTRE_INITIAL}})
    b.utilisateurs.update_many({"centre_id": {"$exists": False}, "role": {"$nin": list(roles.ROLES_GROUPE)}}, {"$set": {"centre_id": CENTRE_INITIAL}})
    b.utilisateurs.update_many({"centre_id": {"$exists": False}}, {"$set": {"centre_id": None}})
    b.jetons_alertes.update_many({"centre_id": {"$exists": False}}, {"$set": {"centre_id": CENTRE_INITIAL}})


def _prefixe(corps: dict, id_actuel: str = "") -> str:
    """Préfixe des codes patients du centre (2 à 6 lettres ou chiffres, majuscules), unique."""
    p = validation.texte(corps, "prefixe", "Préfixe des codes patients", True, 6).upper()
    if not re.fullmatch(r"[A-Z0-9]{2,6}", p):
        validation.erreur("Préfixe : 2 à 6 lettres ou chiffres (exemple : CMC)")
    autre = db.brut().centres.find_one({"prefixe": p, "id": {"$ne": id_actuel}})
    if autre:
        raise HTTPException(409, "Ce préfixe est déjà utilisé par un autre centre")
    return p


@routeur.get("/centres")
def lister(u: dict = Depends(utilisateur_courant)):
    """Centres visibles : tous pour un compte du groupe (liste du sélecteur), le sien seulement pour les autres."""
    if u["role"] in roles.ROLES_GROUPE and u["groupe"]:
        lignes = db.brut().centres.find({}, {"_id": 0}).sort("nom", 1)
    else:
        lignes = db.brut().centres.find({"id": u["centre_id"]}, {"_id": 0})
    return [_public(c) for c in lignes]


@routeur.post("/centres")
def creer(corps: dict, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Crée un centre (super administrateur seulement)."""
    nom = validation.texte(corps, "nom", "Nom du centre", True, 80)
    doc = {"id": str(uuid.uuid4()), "nom": nom, "prefixe": _prefixe(corps), "ville": validation.texte(corps, "ville", "Ville", False, 80),
           "telephone": validation.texte(corps, "telephone", "Téléphone", False, 30), "actif": True, "cree_le": db.maintenant()}
    db.brut().centres.insert_one(doc)
    journaliser("centre_cree", u, f"{nom} ({doc['prefixe']})")
    return _public(doc)


@routeur.put("/centres/{id_}")
def modifier(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Modifie le nom, la ville, le téléphone ou l'état (actif / désactivé) d'un centre. Le préfixe ne change plus une fois des patients créés."""
    c = db.brut().centres.find_one({"id": id_})
    if not c:
        raise HTTPException(404, "Centre introuvable")
    maj: dict = {}
    for cle, libelle, long_ in (("nom", "Nom du centre", 80), ("ville", "Ville", 80), ("telephone", "Téléphone", 30)):
        if cle in corps:
            maj[cle] = validation.texte(corps, cle, libelle, cle == "nom", long_)
    if "prefixe" in corps and str(corps["prefixe"]).upper() != c["prefixe"]:
        if db.brut().patients.count_documents({"centre_id": id_}):
            raise HTTPException(409, "Le préfixe ne peut plus changer : des patients portent déjà ce préfixe")
        maj["prefixe"] = _prefixe(corps, id_)
    if "actif" in corps:
        maj["actif"] = bool(corps["actif"])
    if maj:
        db.brut().centres.update_one({"id": id_}, {"$set": maj})
        journaliser("centre_modifie", u, f"{c['nom']} : {', '.join(sorted(maj))}")
    return _public(db.brut().centres.find_one({"id": id_}))
