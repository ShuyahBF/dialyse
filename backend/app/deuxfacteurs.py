"""
Lot 8 — authentification à deux facteurs (TOTP, norme RFC 6238 : Google Authenticator, FreeOTP, Microsoft Authenticator…).
Implémentée avec la seule bibliothèque standard. Le secret est généré côté serveur, jamais renvoyé après l'activation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

from fastapi import APIRouter, Depends, HTTPException

from . import db, securite
from .auth import journaliser, utilisateur_courant

routeur = APIRouter()
PAS = 30            # un code vaut 30 secondes
CHIFFRES = 6


def nouveau_secret() -> str:
    """Secret aléatoire de 160 bits, en base32 (format attendu par les applications d'authentification)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_a(secret: str, instant: float) -> str:
    """Code à 6 chiffres valable à l'instant donné."""
    cle = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    compteur = int(instant // PAS)
    h = hmac.new(cle, struct.pack(">Q", compteur), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    valeur = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** CHIFFRES)
    return str(valeur).zfill(CHIFFRES)


def verifier_code(secret: str, code: str, dernier_compteur: int = 0, maintenant: float | None = None) -> int | None:
    """
    Vérifie un code (tolérance ± 1 pas pour les horloges décalées). Renvoie le compteur accepté, ou None.
    Un compteur déjà utilisé n'est jamais accepté deux fois (protection contre le rejeu d'un code espionné).
    """
    maintenant = time.time() if maintenant is None else maintenant
    code = str(code).strip().replace(" ", "")
    for decalage in (0, -1, 1):
        t = maintenant + decalage * PAS
        compteur = int(t // PAS)
        if compteur > dernier_compteur and hmac.compare_digest(code_a(secret, t), code):
            return compteur
    return None


def uri_otp(login: str, secret: str) -> str:
    """Adresse « otpauth:// » à transformer en code QR pour l'application d'authentification."""
    from urllib.parse import quote
    return f"otpauth://totp/Dialyse:{quote(login)}?secret={secret}&issuer=Dialyse&digits={CHIFFRES}&period={PAS}"


@routeur.post("/auth/2fa/preparer")
def preparer(u: dict = Depends(utilisateur_courant)):
    """Génère un secret en attente d'activation ; l'utilisateur le saisit (ou scanne le QR) dans son application."""
    secret = nouveau_secret()
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": {"totp_secret_attente": secret}})
    return {"secret": secret, "uri": uri_otp(u["login"], secret)}


@routeur.post("/auth/2fa/activer")
def activer(corps: dict, u: dict = Depends(utilisateur_courant)):
    """Active la double authentification après saisie d'un code valide (preuve que l'application est bien configurée)."""
    fiche = db.base().utilisateurs.find_one({"id": u["id"]})
    secret = fiche.get("totp_secret_attente")
    if not secret:
        raise HTTPException(400, "Demandez d'abord un secret (préparer)")
    compteur = verifier_code(secret, str(corps.get("code", "")))
    if compteur is None:
        raise HTTPException(400, "Code incorrect")
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": {"totp_secret": secret, "totp_actif": True, "totp_dernier": compteur},
                                                         "$unset": {"totp_secret_attente": ""}})
    journaliser("2fa_activee", u)
    return {"ok": True}


@routeur.post("/auth/2fa/desactiver")
def desactiver(corps: dict, u: dict = Depends(utilisateur_courant)):
    """Désactive la double authentification : mot de passe ET code valide exigés."""
    fiche = db.base().utilisateurs.find_one({"id": u["id"]})
    if not fiche.get("totp_actif"):
        return {"ok": True}
    if not securite.verifier_mot_de_passe(str(corps.get("mot_de_passe", "")), fiche["mot_de_passe_hash"]):
        raise HTTPException(400, "Mot de passe incorrect")
    if verifier_code(fiche["totp_secret"], str(corps.get("code", "")), fiche.get("totp_dernier", 0)) is None:
        raise HTTPException(400, "Code incorrect")
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": {"totp_actif": False}, "$unset": {"totp_secret": "", "totp_dernier": ""}})
    journaliser("2fa_desactivee", u)
    return {"ok": True}
