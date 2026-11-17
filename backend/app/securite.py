"""
Mots de passe (scrypt, bibliothèque standard) et jetons de connexion (JWT HS256).
Aucun mot de passe n'est jamais stocké ni journalisé en clair.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

import jwt

from .config import DUREE_JETON_HEURES, env


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    """Empreinte « scrypt$sel$hash » (sel aléatoire propre à chaque mot de passe)."""
    sel = os.urandom(16)
    h = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(sel).decode() + "$" + base64.b64encode(h).decode()


def verifier_mot_de_passe(mot_de_passe: str, empreinte: str) -> bool:
    """Compare en temps constant ; False si l'empreinte est illisible."""
    try:
        _, sel_b64, h_b64 = empreinte.split("$")
        sel, attendu = base64.b64decode(sel_b64), base64.b64decode(h_b64)
        calcule = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calcule, attendu)
    except Exception:
        return False


def mot_de_passe_assez_fort(mot_de_passe: str) -> bool:
    """Au moins 8 caractères, avec une lettre et un chiffre."""
    return len(mot_de_passe) >= 8 and any(c.isalpha() for c in mot_de_passe) and any(c.isdigit() for c in mot_de_passe)


def _secret() -> str:
    s = env("JWT_SECRET")
    if len(s) < 16:
        raise RuntimeError("JWT_SECRET absent ou trop court (16 caractères minimum) : à définir dans les variables d'environnement.")
    return s


def creer_jeton(utilisateur_id: str, role: str) -> str:
    """Jeton signé valable DUREE_JETON_HEURES heures."""
    maintenant = int(time.time())
    return jwt.encode({"sub": utilisateur_id, "role": role, "iat": maintenant,
                       "exp": maintenant + DUREE_JETON_HEURES * 3600}, _secret(), algorithm="HS256")


def lire_jeton(jeton: str) -> dict | None:
    """Contenu du jeton, ou None s'il est invalide ou expiré."""
    try:
        return jwt.decode(jeton, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
