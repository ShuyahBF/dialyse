"""
Sauvegardes chiffrées et restaurations (lot 6).

Principes (tirés d'une perte de données réelle sur une autre plateforme du propriétaire) :
  1. une sauvegarde n'est comptée que si elle a été RELUE : après création, elle est déchiffrée, décompressée et ses compteurs de
     documents sont comparés à ceux de la base (« vérifiée ») ;
  2. AVANT toute restauration, une copie de sécurité (« avant_restauration ») est créée et vérifiée ;
  3. la restauration est précédée d'un APERÇU (comparaison base actuelle / sauvegarde) et exige de taper « RESTAURER » ;
  4. après restauration, les compteurs sont revérifiés ; au moindre écart ou erreur, la copie de sécurité est remise AUTOMATIQUEMENT ;
  5. le journal d'audit actuel n'est JAMAIS remplacé (on ne perd pas la preuve de qui a restauré quoi) ;
  6. on ne restaure pas une sauvegarde dans laquelle le compte du super administrateur qui restaure n'existe pas (pas de verrouillage).
Chiffrement : gzip puis Fernet (AES-128-CBC + HMAC), clé dérivée de la variable d'environnement SAUVEGARDE_CLE (16 caractères minimum,
saisie par le propriétaire dans Render, JAMAIS dans le dépôt). Sans cette clé, aucune sauvegarde n'est lisible : à garder en lieu sûr.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from . import db, roles
from .auth import exiger_roles, journaliser
from .config import env

routeur = APIRouter()

# Données de travail sauvegardées (les sauvegardes elles-mêmes sont exclues).
COLLECTIONS = ["utilisateurs", "parametres", "patients", "postes", "seances", "bilans", "articles", "lots", "mouvements",
               "tarifs", "organismes", "factures", "historique", "passkeys", "biometries", "journal"]
NON_RESTAUREES = {"journal"}                  # le journal d'audit actuel est conservé
MORCEAU = 4 * 1024 * 1024                     # morceaux de 4 Mo (limite de 16 Mo par document MongoDB)
CONSERVER = {"auto": 14, "manuelle": 10, "avant_restauration": 3, "importee": 5}
CONFIRMATION = "RESTAURER"


# ---------- chiffrement ----------

def cle_configuree() -> bool:
    return len(env("SAUVEGARDE_CLE")) >= 16


def _fernet() -> Fernet:
    cle = env("SAUVEGARDE_CLE")
    if len(cle) < 16:
        raise HTTPException(503, "SAUVEGARDE_CLE absente ou trop courte (16 caractères minimum) : à définir dans Render")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("dialyse|" + cle).encode()).digest()))


def empreinte_cle() -> str:
    """8 premiers caractères de l'empreinte de la clé : permet de savoir si une sauvegarde a été faite avec la clé actuelle (sans la révéler)."""
    return hashlib.sha256(("empreinte|dialyse|" + env("SAUVEGARDE_CLE")).encode()).hexdigest()[:8] if cle_configuree() else ""


def chiffrer(contenu: dict) -> bytes:
    return _fernet().encrypt(gzip.compress(json.dumps(contenu, default=str).encode()))


def dechiffrer(donnees: bytes) -> dict:
    try:
        return json.loads(gzip.decompress(_fernet().decrypt(donnees)))
    except (InvalidToken, OSError, ValueError):
        raise HTTPException(400, "Sauvegarde illisible : mauvaise clé de chiffrement ou fichier corrompu")


def lire_base() -> dict:
    """Contenu actuel de toutes les collections sauvegardées."""
    return {"version": 1, "date": db.maintenant(), "collections": {c: list(db.base()[c].find({}, {"_id": 0})) for c in COLLECTIONS}}


def compteurs_base() -> dict:
    return {c: db.base()[c].count_documents({}) for c in COLLECTIONS}


# ---------- stockage ----------

def _lire_octets(ident: str) -> bytes:
    return b"".join(m["donnees"] for m in db.base().sauvegardes_morceaux.find({"sauvegarde_id": ident}).sort("n", 1))


def _ranger(donnees: bytes, compteurs: dict, origine: str, auteur: str, jour: str = "") -> dict:
    """Range une sauvegarde chiffrée (morceaux de 4 Mo) et applique la rétention de son origine. Elle est créée NON vérifiée."""
    ident = str(uuid.uuid4())
    morceaux = [donnees[i:i + MORCEAU] for i in range(0, len(donnees), MORCEAU)] or [b""]
    for n, m in enumerate(morceaux):
        db.base().sauvegardes_morceaux.insert_one({"sauvegarde_id": ident, "n": n, "donnees": m})
    fiche = {"id": ident, "cree_le": db.maintenant(), "jour": jour or db.maintenant()[:10], "origine": origine, "par": auteur, "taille": len(donnees), "morceaux": len(morceaux),
             "sha256": hashlib.sha256(donnees).hexdigest(), "compteurs": compteurs, "total": sum(compteurs.values()), "cle": empreinte_cle(), "verifiee": False}
    db.base().sauvegardes.insert_one(fiche)
    for ancienne in list(db.base().sauvegardes.find({"origine": origine}, {"_id": 0, "id": 1}).sort("cree_le", -1))[CONSERVER[origine]:]:
        _supprimer(ancienne["id"])
    return fiche


def _supprimer(ident: str) -> None:
    db.base().sauvegardes_morceaux.delete_many({"sauvegarde_id": ident})
    db.base().sauvegardes.delete_one({"id": ident})


def verifier(ident: str) -> dict:
    """
    Relit la sauvegarde STOCKÉE : empreinte du fichier, déchiffrement, décompression, compteurs égaux à ceux enregistrés.
    Marque « vérifiée » (ou lève une erreur 409 avec la raison). Renvoie la fiche.
    """
    f = db.base().sauvegardes.find_one({"id": ident})
    if not f:
        raise HTTPException(404, "Sauvegarde introuvable")
    donnees = _lire_octets(ident)
    if hashlib.sha256(donnees).hexdigest() != f["sha256"]:
        db.base().sauvegardes.update_one({"id": ident}, {"$set": {"verifiee": False, "erreur": "empreinte du fichier différente"}})
        raise HTTPException(409, "Sauvegarde corrompue : l'empreinte du fichier ne correspond plus")
    contenu = dechiffrer(donnees)
    lus = {c: len(contenu.get("collections", {}).get(c, [])) for c in f["compteurs"]}       # seulement les collections présentes à la création (anciennes sauvegardes)
    if lus != f["compteurs"]:
        db.base().sauvegardes.update_one({"id": ident}, {"$set": {"verifiee": False, "erreur": "nombre de documents différent"}})
        raise HTTPException(409, "Sauvegarde incohérente : le nombre de documents relu ne correspond pas")
    db.base().sauvegardes.update_one({"id": ident}, {"$set": {"verifiee": True, "verifiee_le": db.maintenant()}, "$unset": {"erreur": ""}})
    return {k: v for k, v in db.base().sauvegardes.find_one({"id": ident}).items() if k != "_id"}


def creer(origine: str, auteur: str, jour: str = "") -> dict:
    """Crée ET VÉRIFIE une sauvegarde de la base actuelle. Une sauvegarde qui ne se relit pas est supprimée et signalée."""
    contenu = lire_base()
    compteurs = {c: len(contenu["collections"][c]) for c in COLLECTIONS}
    fiche = _ranger(chiffrer(contenu), compteurs, origine, auteur, jour)
    try:
        return verifier(fiche["id"])
    except HTTPException:
        _supprimer(fiche["id"])
        raise HTTPException(500, "La sauvegarde créée n'a pas pu être relue : elle a été supprimée. Réessayez ; si le problème persiste, contactez le support.")


def sauvegarde_automatique(maintenant: datetime | None = None) -> bool:
    """Une fois par jour à partir de 02h00 UTC (vérifiée toutes les 10 minutes par la tâche de fond). Vrai si créée ; jamais d'exception."""
    if not cle_configuree():
        return False
    maintenant = maintenant or datetime.now(timezone.utc)
    if maintenant.hour < 2 or db.base().sauvegardes.find_one({"origine": "auto", "jour": maintenant.date().isoformat()}):
        return False
    creer("auto", "automatique", maintenant.date().isoformat())
    return True


# ---------- restauration ----------

def _appliquer(contenu: dict) -> None:
    """Remplace le contenu des collections restaurables par celui de `contenu` (le journal n'est jamais touché)."""
    for c in COLLECTIONS:
        if c in NON_RESTAUREES:
            continue
        if c not in contenu.get("collections", {}):          # collection absente d'une ancienne sauvegarde : on ne la vide pas
            continue
        docs = contenu["collections"][c]
        db.base()[c].delete_many({})
        if docs:
            db.base()[c].insert_many([dict(d) for d in docs])


def restaurer(ident: str, acteur: dict) -> dict:
    """Restauration sûre : copie de sécurité vérifiée → remplacement → contrôle des compteurs → retour arrière automatique si écart."""
    f = verifier(ident)                                           # relit et valide la sauvegarde à restaurer
    contenu = dechiffrer(_lire_octets(ident))
    if not any(u.get("login") == acteur["login"] and u.get("role") == roles.SUPER_ADMIN for u in contenu["collections"].get("utilisateurs", [])):
        raise HTTPException(409, "Votre compte super administrateur n'existe pas dans cette sauvegarde : restauration refusée pour ne pas vous verrouiller")
    secours = creer("avant_restauration", acteur["login"])        # copie de sécurité de l'état ACTUEL (vérifiée)
    try:
        _appliquer(contenu)
        attendu = {c: n for c, n in f["compteurs"].items() if c not in NON_RESTAUREES}
        obtenu = {c: n for c, n in compteurs_base().items() if c not in NON_RESTAUREES}
        if attendu != obtenu:
            raise RuntimeError("écart de compteurs après restauration")
    except Exception as e:
        _appliquer(dechiffrer(_lire_octets(secours["id"])))        # retour arrière AUTOMATIQUE vers l'état d'avant
        journaliser("restauration_annulee", acteur, f"{ident} : {e}")
        raise HTTPException(500, "La restauration a échoué et l'état précédent a été remis automatiquement. Aucune donnée n'a été perdue.")
    journaliser("restauration", acteur, f"{ident} ({f['origine']} du {f['jour']}), copie de sécurité {secours['id']}")
    return {"ok": True, "restaure": f["id"], "copie_de_securite": secours["id"], "documents": f["total"]}


# ---------- routes ----------

def _public(f: dict) -> dict:
    d = {k: v for k, v in f.items() if k not in ("_id", "sha256")}
    d["cle_actuelle"] = bool(f.get("cle")) and f.get("cle") == empreinte_cle()
    return d


@routeur.get("/admin/sauvegardes")
def etat(u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """État des sauvegardes : clé configurée, liste (récentes d'abord), dernière sauvegarde automatique vérifiée."""
    lignes = [_public(f) for f in db.base().sauvegardes.find({}, {"_id": 0}).sort("cree_le", -1)]
    derniere = next((f for f in lignes if f["origine"] == "auto" and f.get("verifiee")), None)
    return {"cle_configuree": cle_configuree(), "heure_auto_utc": 2, "derniere_auto": derniere["cree_le"] if derniere else "",
            "retention": CONSERVER, "sauvegardes": lignes}


@routeur.post("/admin/sauvegardes")
def sauvegarder_maintenant(u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Sauvegarde manuelle immédiate (créée puis vérifiée)."""
    f = creer("manuelle", u["login"])
    journaliser("sauvegarde_creee", u, f"{f['id']} ({f['total']} documents)")
    return _public(f)


@routeur.post("/admin/sauvegardes/{ident}/verifier")
def verifier_route(ident: str, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    f = verifier(ident)
    journaliser("sauvegarde_verifiee", u, ident)
    return _public(f)


@routeur.get("/admin/sauvegardes/{ident}/apercu")
def apercu(ident: str, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Aperçu AVANT restauration : nombre de documents par collection, base actuelle / sauvegarde, et contrôle du compte. Ne modifie rien."""
    f = verifier(ident)
    contenu = dechiffrer(_lire_octets(ident))
    actuel = compteurs_base()
    compte_ok = any(x.get("login") == u["login"] and x.get("role") == roles.SUPER_ADMIN for x in contenu["collections"].get("utilisateurs", []))
    lignes = [{"collection": c, "actuel": actuel[c], "sauvegarde": f["compteurs"][c], "ecart": f["compteurs"][c] - actuel[c], "conservee": c in NON_RESTAUREES} for c in COLLECTIONS if c in f["compteurs"]]
    return {"sauvegarde": _public(f), "lignes": lignes, "compte_present": compte_ok, "cle_actuelle": f.get("cle") == empreinte_cle(), "confirmation": CONFIRMATION}


@routeur.post("/admin/sauvegardes/{ident}/restaurer")
def restaurer_route(ident: str, corps: dict, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Restaure une sauvegarde. Exige la confirmation « RESTAURER » ; crée d'abord une copie de sécurité et revient en arrière en cas d'échec."""
    if str(corps.get("confirmation", "")).strip() != CONFIRMATION:
        raise HTTPException(400, f"Tapez {CONFIRMATION} pour confirmer : la restauration remplace les données actuelles")
    return restaurer(ident, u)


@routeur.get("/admin/sauvegardes/{ident}/fichier")
def fichier(ident: str, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Fichier chiffré (copie hors Render, à garder en lieu sûr : illisible sans la clé de chiffrement)."""
    f = db.base().sauvegardes.find_one({"id": ident})
    if not f:
        raise HTTPException(404, "Sauvegarde introuvable")
    journaliser("sauvegarde_telechargee", u, ident)
    return Response(_lire_octets(ident), media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="sauvegarde-{f["jour"]}-{ident[:8]}.dialyse"'})


@routeur.post("/admin/sauvegardes/importer")
async def importer(requete: Request, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """
    Importe un fichier de sauvegarde (corps brut) comme sauvegarde « importée » après l'avoir déchiffré et contrôlé.
    Il ne restaure rien : on passe ensuite par l'aperçu puis la restauration.
    """
    donnees = await requete.body()
    contenu = dechiffrer(donnees)
    if contenu.get("version") != 1 or "collections" not in contenu:
        raise HTTPException(400, "Fichier de sauvegarde non reconnu")
    compteurs = {c: len(contenu["collections"].get(c, [])) for c in COLLECTIONS}
    fiche = _ranger(donnees, compteurs, "importee", u["login"])
    try:
        f = verifier(fiche["id"])
    except HTTPException:
        _supprimer(fiche["id"])
        raise
    journaliser("sauvegarde_importee", u, f"{f['id']} ({f['total']} documents)")
    return _public(f)


@routeur.delete("/admin/sauvegardes/{ident}")
def supprimer(ident: str, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    if not db.base().sauvegardes.find_one({"id": ident}):
        raise HTTPException(404, "Sauvegarde introuvable")
    _supprimer(ident)
    journaliser("sauvegarde_supprimee", u, ident)
    return {"ok": True}
