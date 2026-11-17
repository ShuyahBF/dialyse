"""
CLÉS D'ACCÈS (WebAuthn) : se connecter au SITE avec l'empreinte, le visage ou le code de l'appareil, sans mot de passe.

  1. ENREGISTREMENT (compte connecté, mot de passe redemandé) : le serveur donne un « défi » aléatoire ; l'appareil crée une paire de clés
     DANS son coffre sécurisé (la clé privée n'en sort jamais) et renvoie la clé PUBLIQUE, que le serveur garde.
  2. CONNEXION : nouveau défi ; l'appareil, après empreinte / visage / code, le SIGNE ; le serveur vérifie avec la clé publique.
     Rien de secret ne transite : un voleur de la base ne peut pas se connecter.
Sécurité : vérification de l'utilisateur EXIGÉE ; défi à usage unique, lié au site (identifiant et adresse contrôlés) et valable 5 minutes ;
compteur de signatures contre les clés clonées ; une connexion par clé d'accès vaut authentification forte (pas de second code).
Adresse du site : FRONTEND_ORIGIN ; identifiant : WEBAUTHN_RP_ID (défaut : domaine du site).
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from webauthn import generate_authentication_options, generate_registration_options, options_to_json, verify_authentication_response, verify_registration_response
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor, ResidentKeyRequirement, UserVerificationRequirement

from . import auth, config, db, securite
from .auth import utilisateur_courant

routeur = APIRouter()
VALIDITE_DEFI_S = 300
NOMBRE_MAX = 10


def _poser_defi(defi: bytes, usage: str, utilisateur_id: str | None = None) -> str:
    ident = str(uuid.uuid4())
    db.base().defis.insert_one({"id": ident, "defi": bytes_to_base64url(defi), "usage": usage, "utilisateur_id": utilisateur_id, "expire": time.time() + VALIDITE_DEFI_S})
    return ident


def _prendre_defi(ident: str, usage: str, utilisateur_id: str | None = None) -> bytes:
    """Rend le défi ET le détruit : un défi ne peut jamais servir deux fois."""
    d = db.base().defis.find_one_and_delete({"id": ident, "usage": usage})
    if not d or time.time() > d.get("expire", 0) or (utilisateur_id and d.get("utilisateur_id") != utilisateur_id):
        raise HTTPException(400, "Demande expirée : recommencez.")
    return base64url_to_bytes(d["defi"])


def _exiger_mot_de_passe(u: dict, mdp: str) -> None:
    fiche = db.base().utilisateurs.find_one({"id": u["id"]})
    if not securite.verifier_mot_de_passe(str(mdp), fiche["mot_de_passe_hash"]):
        raise HTTPException(401, "Mot de passe incorrect")


@routeur.get("/auth/passkey")
def liste(u: dict = Depends(utilisateur_courant)):
    cles = list(db.base().passkeys.find({"utilisateur_id": u["id"]}, {"_id": 0, "credential_id": 1, "nom": 1, "cree_le": 1, "dernier_usage": 1}).sort("cree_le", 1))
    return {"cles": cles, "maximum": NOMBRE_MAX}


@routeur.post("/auth/passkey/options-enregistrement")
def options_enregistrement(corps: dict, u: dict = Depends(utilisateur_courant)):
    """Étape 1 de l'ajout d'une clé : mot de passe redemandé, puis défi + options pour l'appareil."""
    _exiger_mot_de_passe(u, corps.get("mot_de_passe", ""))
    existantes = list(db.base().passkeys.find({"utilisateur_id": u["id"]}, {"_id": 0, "credential_id": 1}))
    if len(existantes) >= NOMBRE_MAX:
        raise HTTPException(409, f"{NOMBRE_MAX} clés au maximum : supprimez-en une d'abord.")
    options = generate_registration_options(
        rp_id=config.rp_id(), rp_name="Dialyse", user_id=u["id"].encode(), user_name=u["login"], user_display_name=u["nom"],
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"])) for c in existantes],
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED))
    return {"defi_id": _poser_defi(options.challenge, "enregistrement", u["id"]), "options": json.loads(options_to_json(options))}


@routeur.post("/auth/passkey/enregistrer")
def enregistrer(corps: dict, u: dict = Depends(utilisateur_courant)):
    defi = _prendre_defi(str(corps.get("defi_id", "")), "enregistrement", u["id"])
    credential = corps.get("credential") or {}
    try:
        verifie = verify_registration_response(credential=credential, expected_challenge=defi, expected_rp_id=config.rp_id(),
                                               expected_origin=config.origines_site(), require_user_verification=True)
    except (InvalidRegistrationResponse, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, "Clé d'accès refusée : la vérification a échoué.") from exc
    identifiant = bytes_to_base64url(verifie.credential_id)
    if db.base().passkeys.find_one({"credential_id": identifiant}, {"_id": 1}):
        raise HTTPException(409, "Cette clé d'accès est déjà enregistrée.")
    nom = str(corps.get("nom") or "").strip()[:40] or f"Clé du {time.strftime('%d/%m/%Y')}"
    db.base().passkeys.insert_one({"credential_id": identifiant, "utilisateur_id": u["id"], "public_key": bytes_to_base64url(verifie.credential_public_key),
                                   "sign_count": verifie.sign_count, "nom": nom, "cree_le": db.maintenant(), "dernier_usage": None})
    auth.journaliser("cle_acces_ajoutee", u, nom)
    return {"ok": True, "nom": nom}


@routeur.post("/auth/passkey/{credential_id}/supprimer")
def supprimer(credential_id: str, corps: dict, u: dict = Depends(utilisateur_courant)):
    _exiger_mot_de_passe(u, corps.get("mot_de_passe", ""))
    if not db.base().passkeys.delete_one({"credential_id": credential_id, "utilisateur_id": u["id"]}).deleted_count:
        raise HTTPException(404, "Clé introuvable.")
    auth.journaliser("cle_acces_supprimee", u)
    return {"ok": True}


@routeur.post("/auth/passkey/options-connexion")
def options_connexion():
    """Défi de connexion SANS identifiant : l'appareil propose la clé d'accès du site qu'il possède (clé « découvrable »)."""
    options = generate_authentication_options(rp_id=config.rp_id(), user_verification=UserVerificationRequirement.REQUIRED)
    return {"defi_id": _poser_defi(options.challenge, "connexion"), "options": json.loads(options_to_json(options))}


@routeur.post("/auth/passkey/connexion")
def connexion(corps: dict):
    defi = _prendre_defi(str(corps.get("defi_id", "")), "connexion")
    credential = corps.get("credential") or {}

    def refuser(u: dict | None = None):
        if u:
            auth.echec_acces(u, "clé d'accès refusée")
        raise HTTPException(401, "Connexion par clé d'accès refusée.")

    identifiant = str(credential.get("id") or credential.get("rawId") or "")
    cle = db.base().passkeys.find_one({"credential_id": identifiant}, {"_id": 0})
    if not cle:
        refuser()
    u = db.base().utilisateurs.find_one({"id": cle["utilisateur_id"]})
    if not u or not u.get("actif", True):
        refuser()
    auth.verifier_non_bloque(u)
    try:
        verifie = verify_authentication_response(credential=credential, expected_challenge=defi, expected_rp_id=config.rp_id(), expected_origin=config.origines_site(),
                                                 credential_public_key=base64url_to_bytes(cle["public_key"]), credential_current_sign_count=cle["sign_count"],
                                                 require_user_verification=True)
    except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError):
        refuser(u)
    # Compteur de signatures mis à jour en CONDITIONNEL : une même signature ne peut pas servir deux fois en parallèle (clé clonée).
    res = db.base().passkeys.update_one({"credential_id": identifiant, "sign_count": cle["sign_count"]}, {"$set": {"sign_count": verifie.new_sign_count, "dernier_usage": db.maintenant()}})
    if not res.modified_count and verifie.new_sign_count != 0:
        refuser(u)
    return auth.ouvrir_session(u, controle_2fa=False, moyen="clé d'accès")
