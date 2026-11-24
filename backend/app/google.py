"""Connexion par compte Google (Dialyse) : démarrer, retour de Google, échange du code, liaison / déliaison depuis « Mon compte ».
Voir google_auth.py pour le déroulé et les règles de sécurité. Inactif tant que GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET ne sont pas saisis dans Render.
Données de santé : AUCUN compte n'est créé ni rapproché par e-mail ; seul un compte DÉJÀ LIÉ peut se connecter par Google, et la double authentification
(application ou WhatsApp) reste exigée comme pour un mot de passe (`auth.ouvrir_session`)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import auth, db, google_auth, securite
from .config import env, origines_site

routeur = APIRouter(prefix="/auth/google", tags=["Google"])
SCHEMA_APP = "dialyse"            # adresse « dialyse://google?… » captée par l'application Android


def _configure() -> bool:
    return bool(env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"))


def _secret_etat() -> str:
    return env("JWT_SECRET")


def _redirect_uri(request: Request) -> str:
    """Adresse de retour déclarée chez Google (GOOGLE_REDIRECT_URI, sinon déduite de la requête, en https hors poste local)."""
    if env("GOOGLE_REDIRECT_URI"):
        return env("GOOGLE_REDIRECT_URI")
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://") and not base.startswith("http://localhost"):
        base = "https://" + base[len("http://"):]
    return f"{base}/auth/google/retour"


def _vers_site(cible: str, **params):
    """Renvoie la personne au site (web) ou à l'application (page avec bouton « Retourner dans l'application », le navigateur pouvant bloquer une redirection directe)."""
    params = {k: v for k, v in params.items() if v}
    if cible == "app":
        lien = f"{SCHEMA_APP}://google?{urllib.parse.urlencode(params)}"
        return HTMLResponse(f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Dialyse</title>"
                            f"<body style='font-family:sans-serif;text-align:center;padding:2rem'><p>Retour dans l'application Dialyse…</p>"
                            f"<p><a href=\"{escape(lien)}\" style='display:inline-block;padding:1rem 2rem;background:#03316e;color:#fff;border-radius:2rem;text-decoration:none'>Retourner dans l'application</a></p>"
                            f"<script>location.href={json.dumps(lien)}</script></body>")
    origine = (origines_site() or ["http://localhost:5173"])[0]
    return RedirectResponse(f"{origine}/connexion-google?{urllib.parse.urlencode(params)}", status_code=302)


def _echanger_code(code: str, redirect_uri: str) -> dict | None:
    """Échange le code contre l'identité (appel externe, seulement ici). Rend { sub, email, nom } ou None. Remplacé par un faux dans les tests."""
    corps = urllib.parse.urlencode({"code": code, "client_id": env("GOOGLE_CLIENT_ID"), "client_secret": env("GOOGLE_CLIENT_SECRET"),
                                    "redirect_uri": redirect_uri, "grant_type": "authorization_code"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(google_auth.URL_JETON, data=corps, method="POST"), timeout=10) as r:
            return google_auth.identite_depuis_jeton(json.loads(r.read()).get("id_token", ""), env("GOOGLE_CLIENT_ID"))
    except (urllib.error.URLError, ValueError, OSError):
        return None


@routeur.get("/config")
def config():
    """Le site n'affiche le bouton Google que si le serveur est configuré."""
    return {"disponible": _configure()}


@routeur.get("/demarrer")
def demarrer(request: Request, cible: str = "web"):
    if not _configure():
        raise HTTPException(503, "La connexion par Google n'est pas encore activée")
    etat = google_auth.signer_etat(cible, None, _secret_etat())
    return RedirectResponse(google_auth.url_demarrage(env("GOOGLE_CLIENT_ID"), _redirect_uri(request), etat), status_code=302)


class DemandeLiaison(BaseModel):
    cible: str = Field("web", max_length=3)


@routeur.post("/lier-url")
def lier_url(data: DemandeLiaison, request: Request, u: dict = Depends(auth.utilisateur_courant)):
    """Adresse de Google pour LIER le compte connecté (l'identité du compte est dans l'état signé)."""
    if not _configure():
        raise HTTPException(503, "La connexion par Google n'est pas encore activée")
    etat = google_auth.signer_etat(data.cible, u["id"], _secret_etat())
    return {"url": google_auth.url_demarrage(env("GOOGLE_CLIENT_ID"), _redirect_uri(request), etat)}


@routeur.get("/retour")
def retour(request: Request, code: str = "", state: str = "", error: str = ""):
    etat = google_auth.lire_etat(state, _secret_etat())
    if not etat:
        return _vers_site("web", erreur="etat")
    cible = etat.get("c", "web")
    if error or not code or not _configure():
        return _vers_site(cible, erreur="refuse")
    identite = _echanger_code(code, _redirect_uri(request))
    if not identite:
        return _vers_site(cible, erreur="google")
    base = db.base()
    existant = base.utilisateurs.find_one({"google.sub": identite["sub"]}, {"_id": 0})
    if etat.get("l"):                                                         # liaison du compte connecté
        if existant and existant["id"] != etat["l"]:
            return _vers_site(cible, erreur="deja_lie")
        base.utilisateurs.update_one({"id": etat["l"]}, {"$set": {"google": {"sub": identite["sub"], "email": identite["email"], "lie_le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}})
        return _vers_site(cible, lie="1")
    if not existant:                                                          # connexion : seulement un compte déjà lié
        return _vers_site(cible, erreur="aucun_compte")
    if not existant.get("actif", True):
        return _vers_site(cible, erreur="bloque")
    clair, empreinte = google_auth.nouveau_code()
    base.google_codes.insert_one({"empreinte": empreinte, "user_id": existant["id"], "expire": time.time() + google_auth.VALIDITE_CODE_S})
    return _vers_site(cible, code=clair)


class Echange(BaseModel):
    code: str = Field(min_length=10, max_length=100)
    code_2fa: str = Field("", max_length=20)        # code de l'application d'authentification ou de WhatsApp, si le compte l'exige


@routeur.post("/echange")
def echange(data: Echange):
    """Le site remet le code à usage unique (reçu de Google) et reçoit le jeton. Le second facteur du compte reste exigé (`ouvrir_session`) :
    tant qu'il manque, le code Google n'est PAS consommé ; il l'est (une seule utilisation) quand la session s'ouvre."""
    base = db.base()
    empreinte = google_auth.empreinte_code(data.code)
    ligne = base.google_codes.find_one({"empreinte": empreinte}, {"_id": 0})
    if not ligne or ligne.get("expire", 0) < time.time():
        raise HTTPException(401, "Connexion Google expirée : recommencez")
    u = base.utilisateurs.find_one({"id": ligne["user_id"]}, {"_id": 0})
    auth.verifier_non_bloque(u)
    if not u or not u.get("actif", True):
        raise HTTPException(401, "Compte indisponible")
    session = auth.ouvrir_session(u, data.code_2fa, moyen="Google")           # lève CODE_2FA_REQUIS / CODE_WA_REQUIS / code incorrect
    if not base.google_codes.find_one_and_delete({"empreinte": empreinte}):
        raise HTTPException(401, "Connexion Google expirée : recommencez")
    return session


@routeur.get("/etat")
def etat(u: dict = Depends(auth.utilisateur_courant)):
    fiche = db.base().utilisateurs.find_one({"id": u["id"]}, {"_id": 0}) or {}
    g = fiche.get("google") or {}
    return {"disponible": _configure(), "lie": bool(g.get("sub")), "email": g.get("email", ""), "lie_le": g.get("lie_le", "")}


class Deliaison(BaseModel):
    mot_de_passe: str = Field(min_length=1, max_length=128)


@routeur.post("/delier")
def delier(data: Deliaison, u: dict = Depends(auth.utilisateur_courant)):
    """Retire la liaison : le mot de passe est redemandé (on prouve qu'on est le titulaire)."""
    fiche = db.base().utilisateurs.find_one({"id": u["id"]}, {"_id": 0}) or {}
    auth.verifier_non_bloque(fiche)
    if not securite.verifier_mot_de_passe(data.mot_de_passe, fiche.get("mot_de_passe_hash", "")):
        auth.echec_acces(fiche, "retrait de la liaison Google : mot de passe incorrect")
        raise HTTPException(401, "Mot de passe incorrect")
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$unset": {"google": ""}})
    auth.journaliser("google_delie", {"id": u["id"], "login": u["login"], "role": u["role"], "centre_id": u.get("centre_id")}, "")
    return {"ok": True}
