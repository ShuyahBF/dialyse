"""
MODÈLES de dossier d'adhésion à la file active d'un centre de dialyse (demande du propriétaire, 17/11/2026).

Un MODÈLE = la liste des pièces à fournir pour ouvrir un dossier. Le modèle par défaut reprend la liste communiquée (pièce d'identité, bulletin de référence, bilans,
sérologies, échographie rénale, certificat d'indigence). Chaque centre peut AVOIR SES VARIANTES ou son modèle propre : l'administration crée, duplique, modifie les modèles ;
chaque patient est rattaché à un modèle (à défaut, le modèle par défaut). On suit seulement la RÉCEPTION de chaque pièce, jamais son contenu.
Les clés des pièces sont STABLES : renommer une pièce ne perd pas son état chez les patients.
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException

from . import db, roles
from .auth import exiger_roles, journaliser

routeur = APIRouter()

ID_DEFAUT = "defaut"
PIECES_DEFAUT = [
    {"cle": "identite", "libelle": "Pièce d'identité valide (CNIB ou passeport)", "obligatoire": True},
    {"cle": "reference", "libelle": "Bulletin de référence ou dossier médical (courrier d'un médecin attestant une insuffisance rénale nécessitant une épuration extrarénale)", "obligatoire": True},
    {"cle": "bilans", "libelle": "Bilans biologiques récents (créatininémie, urée, ionogramme sanguin, numération formule sanguine)", "obligatoire": True},
    {"cle": "serologies", "libelle": "Sérologies obligatoires (hépatites B et C, VIH), pour l'orientation vers les générateurs adaptés", "obligatoire": True},
    {"cle": "echographie", "libelle": "Échographie rénale (compte-rendu : atteinte aiguë ou chronique)", "obligatoire": True},
    {"cle": "indigence", "libelle": "Certificat d'indigence, si applicable (délivré par l'action sociale : exonération des frais annexes et examens complémentaires)", "obligatoire": False},
]
ETATS_PIECE = ["manquante", "recue", "sans_objet"]
MAX_PIECES = 30


def _defaut() -> dict:
    return {"id": ID_DEFAUT, "nom": "Modèle national — file active des centres de dialyse", "centre": "", "pieces": [dict(p) for p in PIECES_DEFAUT],
            "par_defaut": True, "cree_le": db.maintenant()}


def tous() -> list[dict]:
    """Tous les modèles (le modèle par défaut est créé à la première lecture) ; le modèle par défaut en premier."""
    b = db.base()
    if b.modeles_adhesion.count_documents({}) == 0:
        b.modeles_adhesion.insert_one(_defaut())
    return sorted(b.modeles_adhesion.find({}, {"_id": 0}), key=lambda m: (not m.get("par_defaut"), m.get("nom", "").lower()))


def dictionnaire() -> dict:
    """{id: modèle} : lu UNE fois pour toute une liste de patients (règle 7 : pas de lecture par ligne)."""
    return {m["id"]: m for m in tous()}


def modele_de(patient: dict, modeles: dict) -> dict:
    """Modèle d'un patient : celui choisi, sinon (ou s'il a disparu) le modèle par défaut."""
    m = modeles.get(patient.get("modele_adhesion_id") or "")
    if m:
        return m
    return next((x for x in modeles.values() if x.get("par_defaut")), None) or next(iter(modeles.values()))


def etat_dossier(pieces: dict | None, modele_pieces: list[dict]) -> dict:
    """Fonction PURE : avancement du dossier. Complet = toutes les pièces OBLIGATOIRES du modèle sont reçues (les facultatives ne comptent pas)."""
    pieces = pieces or {}
    obligatoires = [x["cle"] for x in modele_pieces if x.get("obligatoire")]
    manquantes = [c for c in obligatoires if (pieces.get(c) or {}).get("statut") != "recue"]
    return {"recues": len(obligatoires) - len(manquantes), "total": len(obligatoires), "complet": not manquantes, "manquantes": manquantes}


def valider_modele(corps: dict, existant: dict | None = None) -> dict:
    """Nom, centre facultatif, liste de pièces (libellé, obligatoire). Les clés existantes sont conservées ; une nouvelle pièce reçoit une clé stable."""
    nom = str(corps.get("nom") or "").strip()
    if not 3 <= len(nom) <= 80:
        raise HTTPException(422, "Le nom du modèle doit faire de 3 à 80 caractères")
    brutes = corps.get("pieces")
    if not isinstance(brutes, list) or not 1 <= len(brutes) <= MAX_PIECES:
        raise HTTPException(422, f"Un modèle contient de 1 à {MAX_PIECES} pièces")
    anciennes = {p["cle"] for p in (existant or {}).get("pieces", [])}
    pieces, vues = [], set()
    for x in brutes:
        libelle = str((x or {}).get("libelle") or "").strip()
        if not 3 <= len(libelle) <= 300:
            raise HTTPException(422, "Chaque pièce a un libellé de 3 à 300 caractères")
        cle = str(x.get("cle") or "")
        if not (re.fullmatch(r"[a-z0-9_]{1,40}", cle) and (cle in anciennes or not existant)):
            cle = "p" + uuid.uuid4().hex[:8]                      # nouvelle pièce : clé stable générée par le serveur
        if cle in vues:
            raise HTTPException(422, "Deux pièces ont la même clé")
        vues.add(cle)
        pieces.append({"cle": cle, "libelle": libelle, "obligatoire": bool(x.get("obligatoire", True))})
    if not any(p["obligatoire"] for p in pieces):
        raise HTTPException(422, "Au moins une pièce doit être obligatoire")
    return {"nom": nom, "centre": str(corps.get("centre") or "").strip()[:80], "pieces": pieces}


@routeur.get("/modeles-adhesion")
def lister(u: dict = Depends(exiger_roles(roles.LECTURE_PATIENT))):
    """Modèles de dossier d'adhésion, avec le nombre de patients rattachés (le modèle par défaut compte ceux qui n'ont rien choisi)."""
    b = db.base()
    modeles = tous()
    defaut = next((m["id"] for m in modeles if m.get("par_defaut")), ID_DEFAUT)
    sortie = []
    for m in modeles:
        filtre = {"modele_adhesion_id": m["id"]} if m["id"] != defaut else {"$or": [{"modele_adhesion_id": m["id"]}, {"modele_adhesion_id": {"$in": [None, ""]}}, {"modele_adhesion_id": {"$exists": False}}]}
        sortie.append({**m, "patients": b.patients.count_documents(filtre)})
    return {"modeles": sortie, "etats": ETATS_PIECE}


@routeur.post("/modeles-adhesion")
def creer(corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Crée un modèle (variante ou modèle propre d'un centre). Si `copie_de` est donné, on part des pièces de ce modèle."""
    base = next((m for m in tous() if m["id"] == corps.get("copie_de")), None)
    if base and not corps.get("pieces"):
        corps = {**corps, "pieces": base["pieces"]}
    # Une copie reçoit de nouvelles clés (un modèle indépendant) : `existant` absent
    valide = valider_modele(corps, None)
    m = {"id": str(uuid.uuid4()), **valide, "par_defaut": False, "cree_le": db.maintenant(), "cree_par": u["login"]}
    db.base().modeles_adhesion.insert_one(dict(m))
    journaliser("modele_adhesion_cree", u, m["nom"])
    return m


@routeur.put("/modeles-adhesion/{id_}")
def modifier(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    existant = next((m for m in tous() if m["id"] == id_), None)
    if not existant:
        raise HTTPException(404, "Modèle introuvable")
    valide = valider_modele(corps, existant)
    db.base().modeles_adhesion.update_one({"id": id_}, {"$set": {**valide, "maj_le": db.maintenant(), "maj_par": u["login"]}})
    journaliser("modele_adhesion_modifie", u, valide["nom"])
    return next(m for m in tous() if m["id"] == id_)


@routeur.post("/modeles-adhesion/{id_}/defaut")
def definir_defaut(id_: str, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Définit le modèle appliqué aux patients qui n'en ont pas choisi."""
    if not any(m["id"] == id_ for m in tous()):
        raise HTTPException(404, "Modèle introuvable")
    b = db.base()
    b.modeles_adhesion.update_many({}, {"$set": {"par_defaut": False}})
    b.modeles_adhesion.update_one({"id": id_}, {"$set": {"par_defaut": True}})
    journaliser("modele_adhesion_defaut", u, id_)
    return {"ok": True}


@routeur.delete("/modeles-adhesion/{id_}")
def supprimer(id_: str, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Supprime un modèle : refusé s'il est le modèle par défaut ou si des patients lui sont rattachés."""
    m = next((x for x in tous() if x["id"] == id_), None)
    if not m:
        raise HTTPException(404, "Modèle introuvable")
    if m.get("par_defaut"):
        raise HTTPException(409, "Le modèle par défaut ne se supprime pas : définissez d'abord un autre modèle par défaut")
    if db.base().patients.count_documents({"modele_adhesion_id": id_}):
        raise HTTPException(409, "Des patients sont rattachés à ce modèle : changez leur modèle d'abord")
    db.base().modeles_adhesion.delete_one({"id": id_})
    journaliser("modele_adhesion_supprime", u, m["nom"])
    return {"ok": True}
