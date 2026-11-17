"""Authentification : connexion, jeton, utilisateur courant, blocage après échecs répétés, journal d'audit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException

from . import db, securite
from .config import BLOCAGE_MINUTES, TENTATIVES_MAX


def journaliser(action: str, acteur: dict | None, detail: str = "") -> None:
    """Ajoute une ligne au journal (qui, quoi, quand). Jamais de mot de passe ni de donnée médicale : seulement des références."""
    a = acteur or {}
    db.base().journal.insert_one({"quand": db.maintenant(), "action": action, "acteur_id": a.get("id"),
                                  "acteur": a.get("login"), "role": a.get("role"), "detail": detail[:300]})


def utilisateur_courant(authorization: str = Header(default="")) -> dict:
    """Utilisateur déduit du jeton « Bearer … » ; 401 si jeton invalide ou compte désactivé."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Connexion requise")
    contenu = securite.lire_jeton(authorization[7:].strip())
    if not contenu:
        raise HTTPException(401, "Session expirée, reconnectez-vous")
    u = db.base().utilisateurs.find_one({"id": contenu["sub"]})
    if not u or not u.get("actif", True):
        raise HTTPException(401, "Compte inconnu ou désactivé")
    # Le rôle vient de la base (pas du jeton) : un changement de rôle ou une désactivation est immédiat.
    return {"id": u["id"], "login": u["login"], "nom": u.get("nom_affiche", u["login"]), "role": u["role"],
            "doit_changer_mdp": bool(u.get("doit_changer_mdp")), "totp_actif": bool(u.get("totp_actif"))}


def exiger_roles(*roles):
    """Dépendance FastAPI : refuse (403) tout rôle hors de la liste."""
    autorises = set()
    for r in roles:
        autorises |= set(r) if isinstance(r, (set, frozenset, list, tuple)) else {r}

    def verif(u: dict = Depends(utilisateur_courant)) -> dict:
        if u["role"] not in autorises:
            raise HTTPException(403, "Droits insuffisants")
        return u
    return verif


def _compter_echec(u: dict, maintenant: datetime) -> None:
    """Un échec de plus ; au-delà de TENTATIVES_MAX de suite, le compte est bloqué BLOCAGE_MINUTES minutes."""
    n = u.get("echecs", 0) + 1
    maj = {"echecs": n}
    if n >= TENTATIVES_MAX:
        maj = {"echecs": 0, "bloque_jusqua": (maintenant + timedelta(minutes=BLOCAGE_MINUTES)).isoformat()}
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": maj})


def verifier_non_bloque(u: dict | None) -> None:
    """429 si le compte est bloqué temporairement après trop d'essais."""
    if u and u.get("bloque_jusqua") and datetime.now(timezone.utc) < datetime.fromisoformat(u["bloque_jusqua"]):
        raise HTTPException(429, f"Compte bloqué {BLOCAGE_MINUTES} minutes après trop d'essais")


def connexion(login: str, mot_de_passe: str, code_2fa: str = "") -> dict:
    """
    Vérifie les identifiants ; blocage temporaire après TENTATIVES_MAX échecs de suite.
    Si le compte a la double authentification, un code à 6 chiffres est exigé en plus (détail « CODE_2FA_REQUIS »).
    """
    u = db.base().utilisateurs.find_one({"login": login.strip().lower()})
    verifier_non_bloque(u)
    maintenant = datetime.now(timezone.utc)
    if not u or not u.get("actif", True) or not securite.verifier_mot_de_passe(mot_de_passe, u["mot_de_passe_hash"]):
        if u:
            _compter_echec(u, maintenant)
            journaliser("connexion_refusee", {"id": u["id"], "login": u["login"], "role": u["role"]})
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    acteur = {"id": u["id"], "login": u["login"], "role": u["role"]}
    if u.get("totp_actif"):
        from .deuxfacteurs import verifier_code
        if not code_2fa.strip():
            raise HTTPException(401, "CODE_2FA_REQUIS")
        compteur = verifier_code(u["totp_secret"], code_2fa, u.get("totp_dernier", 0))
        if compteur is None:
            _compter_echec(u, maintenant)
            journaliser("connexion_refusee", acteur, "code 2FA incorrect")
            raise HTTPException(401, "Code de vérification incorrect")
        db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": {"totp_dernier": compteur}})
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": {"echecs": 0, "bloque_jusqua": None}})
    journaliser("connexion", acteur)
    return {"jeton": securite.creer_jeton(u["id"], u["role"]), "role": u["role"], "nom": u.get("nom_affiche", u["login"]),
            "login": u["login"], "doit_changer_mdp": bool(u.get("doit_changer_mdp")), "totp_actif": bool(u.get("totp_actif"))}
