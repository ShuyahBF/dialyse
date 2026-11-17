"""
Moyens d'accès autres que le mot de passe seul (lot 7) :
  1. « Mot de passe oublié » : lien à usage unique envoyé par WhatsApp (page du site pour choisir le nouveau mot de passe) ;
  2. connexion par numéro WhatsApp : code à 6 chiffres reçu sur WhatsApp (valable 5 minutes) ;
  3. code WhatsApp en SECOND facteur (option du compte, pour qui n'a pas d'application d'authentification) ;
  4. empreinte / visage d'un téléphone (application Android) : secret propre à l'appareil, déverrouillé par la biométrie ;
  les clés d'accès du navigateur (WebAuthn) sont dans passkeys.py.
Sécurité : réponses identiques que le compte existe ou non (pas d'énumération), codes hachés en base, 5 essais par code,
5 demandes par heure et par compte, blocage temporaire du compte après trop d'échecs (comme le mot de passe). Les messages
WhatsApp partent EN ARRIÈRE-PLAN (règle 7) et ne contiennent jamais de donnée de patient.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException

from . import auth, db, securite, whatsapp
from .config import origines_site

routeur = APIRouter()
VALIDITE_CODE_MIN = 5            # un code WhatsApp vaut 5 minutes
VALIDITE_LIEN_MIN = 30           # un lien de réinitialisation vaut 30 minutes
ESSAIS_MAX = 5                   # essais par code
CODES_PAR_HEURE = 5              # demandes par compte et par heure
GENERIQUE = {"ok": True, "message": "Si ce compte existe et possède un numéro WhatsApp vérifié, un message vient d'être envoyé."}


# ---------- outils ----------

def _empreinte(valeur: str) -> str:
    """Empreinte HMAC d'un code / lien / secret (la valeur elle-même n'est jamais stockée)."""
    return hmac.new(securite._secret().encode(), valeur.encode(), hashlib.sha256).hexdigest()


def _dans(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _expire(iso: str) -> bool:
    return datetime.now(timezone.utc) >= datetime.fromisoformat(iso)


def trop_de_demandes(u: dict) -> bool:
    """Vrai si ce compte a déjà demandé CODES_PAR_HEURE messages dans l'heure (limite l'abus d'envois WhatsApp)."""
    depuis = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return db.base().envois_acces.count_documents({"utilisateur_id": u["id"], "cree": {"$gt": depuis}}) >= CODES_PAR_HEURE


def noter_demande(u: dict) -> None:
    """Compte une demande de message (le décompte vit à part : un nouveau code annule l'ancien, mais pas son compteur)."""
    db.base().envois_acces.insert_one({"utilisateur_id": u["id"], "cree": datetime.now(timezone.utc).isoformat()})


def lancer(fonction, *arguments) -> None:
    """
    Envoie un message EN ARRIÈRE-PLAN (fil séparé : la requête n'attend jamais l'API WhatsApp, règle 7), y compris quand la requête
    se termine par une erreur 401 (les tâches de fond de FastAPI ne partent pas dans ce cas). WHATSAPP_SYNC=1 : envoi immédiat (tests).
    """
    from .config import env
    if env("WHATSAPP_SYNC") == "1":
        fonction(*arguments)
        return
    import threading
    threading.Thread(target=fonction, args=arguments, daemon=True).start()


def creer_code(u: dict, objet: str, cible: str = "") -> str:
    """Nouveau code à 6 chiffres pour (compte, objet) ; les anciens codes du même objet sont annulés. Renvoie le code EN CLAIR (à envoyer, jamais à stocker)."""
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    b = db.base()
    noter_demande(u)
    b.codes_acces.delete_many({"utilisateur_id": u["id"], "objet": objet, "type": "code"})
    b.codes_acces.insert_one({"id": str(uuid.uuid4()), "type": "code", "utilisateur_id": u["id"], "objet": objet, "cible": cible,
                              "hash": _empreinte(code), "expire": _dans(VALIDITE_CODE_MIN), "essais": 0, "cree": db.maintenant()})
    return code


def controler_code(u: dict, objet: str, code: str) -> dict:
    """Retourne la fiche du code si `code` est juste ; sinon 400 (essai compté, code annulé au bout de ESSAIS_MAX). Usage unique."""
    b = db.base()
    fiche = b.codes_acces.find_one({"utilisateur_id": u["id"], "objet": objet, "type": "code"})
    if not fiche or _expire(fiche["expire"]):
        raise HTTPException(400, "Code expiré ou inconnu : demandez-en un nouveau")
    if not hmac.compare_digest(fiche["hash"], _empreinte(str(code).strip())):
        if fiche["essais"] + 1 >= ESSAIS_MAX:
            b.codes_acces.delete_one({"id": fiche["id"]})
        else:
            b.codes_acces.update_one({"id": fiche["id"]}, {"$inc": {"essais": 1}})
        raise HTTPException(400, "Code incorrect")
    b.codes_acces.delete_one({"id": fiche["id"]})
    return fiche


def utilisateur_par_numero(numero: str) -> dict | None:
    """Compte actif dont le numéro WhatsApp VÉRIFIÉ est `numero` (None sinon)."""
    return db.base().utilisateurs.find_one({"telephone": numero, "telephone_verifie": True, "actif": {"$ne": False}})


def revoquer_acces_appareils(utilisateur_id: str) -> None:
    """Tout changement / réinitialisation de mot de passe annule les empreintes d'appareil ET les clés d'accès (à refaire)."""
    db.base().biometries.delete_many({"utilisateur_id": utilisateur_id})
    db.base().passkeys.delete_many({"utilisateur_id": utilisateur_id})


@routeur.get("/auth/options")
def options():
    """Ce que le serveur sait faire (la page de connexion masque le WhatsApp si le serveur n'est pas configuré)."""
    return {"whatsapp": whatsapp.configure(), "cles_acces": True}


# ---------- 1. mot de passe oublié ----------

@routeur.post("/auth/oubli")
def oubli(corps: dict, fond: BackgroundTasks):
    """Corps : {identifiant} (identifiant de connexion OU numéro WhatsApp). Réponse toujours identique."""
    ident = str(corps.get("identifiant", "")).strip().lower()
    u = db.base().utilisateurs.find_one({"login": ident}) or (utilisateur_par_numero(whatsapp.normaliser_numero(ident)) if ident else None)
    if u and u.get("actif", True) and u.get("telephone_verifie") and u.get("telephone") and whatsapp.configure() and not trop_de_demandes(u):
        jeton = secrets.token_urlsafe(32)
        b = db.base()
        noter_demande(u)
        b.codes_acces.delete_many({"utilisateur_id": u["id"], "type": "lien"})
        b.codes_acces.insert_one({"id": str(uuid.uuid4()), "type": "lien", "utilisateur_id": u["id"], "hash": _empreinte(jeton),
                                  "expire": _dans(VALIDITE_LIEN_MIN), "cree": db.maintenant()})
        site = (origines_site() or [""])[0]
        fond.add_task(whatsapp.envoyer_lien, u["telephone"], f"{site}/reinitialiser?jeton={jeton}")
        auth.journaliser("oubli_mot_de_passe", {"id": u["id"], "login": u["login"], "role": u["role"]}, "lien envoyé par WhatsApp")
    return GENERIQUE


@routeur.post("/auth/reinitialiser")
def reinitialiser(corps: dict):
    """Corps : {jeton, mot_de_passe}. Lien à usage unique ; le compte est débloqué ; empreintes et clés d'accès annulées."""
    b = db.base()
    fiche = b.codes_acces.find_one({"type": "lien", "hash": _empreinte(str(corps.get("jeton", "")))})
    if not fiche or _expire(fiche["expire"]):
        raise HTTPException(400, "Lien invalide ou expiré : refaites la demande « Mot de passe oublié »")
    mdp = str(corps.get("mot_de_passe", ""))
    if not securite.mot_de_passe_assez_fort(mdp):
        raise HTTPException(400, "Mot de passe trop faible : 8 caractères au moins, avec une lettre et un chiffre")
    u = b.utilisateurs.find_one({"id": fiche["utilisateur_id"]})
    if not u:
        raise HTTPException(400, "Lien invalide ou expiré")
    b.utilisateurs.update_one({"id": u["id"]}, {"$set": {"mot_de_passe_hash": securite.hacher_mot_de_passe(mdp), "doit_changer_mdp": False, "echecs": 0, "bloque_jusqua": None}})
    b.codes_acces.delete_many({"utilisateur_id": u["id"], "type": "lien"})
    revoquer_acces_appareils(u["id"])
    auth.journaliser("mot_de_passe_reinitialise", {"id": u["id"], "login": u["login"], "role": u["role"]}, "par lien WhatsApp")
    return {"ok": True}


# ---------- 2. connexion par numéro WhatsApp ----------

@routeur.post("/auth/otp/demande")
def otp_demande(corps: dict, fond: BackgroundTasks):
    """Corps : {telephone}. Réponse toujours identique (le serveur ne révèle pas si le numéro est connu)."""
    if not whatsapp.configure():
        raise HTTPException(503, "La connexion par WhatsApp n'est pas encore activée sur le serveur")
    numero = whatsapp.normaliser_numero(str(corps.get("telephone", "")))
    u = utilisateur_par_numero(numero) if numero else None
    if u and not trop_de_demandes(u):
        fond.add_task(whatsapp.envoyer_code, numero, creer_code(u, "connexion"), "connexion")
    return GENERIQUE


@routeur.post("/auth/otp/verifier")
def otp_verifier(corps: dict):
    """Corps : {telephone, code, code_2fa?}. Ouvre la session comme le mot de passe (l'application d'authentification reste exigée si activée)."""
    numero = whatsapp.normaliser_numero(str(corps.get("telephone", "")))
    u = utilisateur_par_numero(numero) if numero else None
    if not u:
        raise HTTPException(400, "Code incorrect")
    auth.verifier_non_bloque(u)
    try:
        controler_code(u, "connexion", str(corps.get("code", "")))
    except HTTPException:
        auth.echec_acces(u, "code WhatsApp incorrect")
        raise
    # Le code WhatsApp remplace le mot de passe ; un second facteur par application d'authentification, s'il est actif, reste exigé.
    return auth.ouvrir_session(u, str(corps.get("code_2fa", "")), moyen="code WhatsApp")


# ---------- numéro WhatsApp du compte (à vérifier une fois) ----------

@routeur.get("/compte/acces")
def etat_acces(u: dict = Depends(auth.utilisateur_courant), x_appareil: str = Header(default="")):
    """État des moyens d'accès du compte : numéro (masqué), vérifié ou non, second facteur WhatsApp, clés d'accès, empreinte de CET appareil."""
    fiche = db.base().utilisateurs.find_one({"id": u["id"]}) or {}
    return {"whatsapp_disponible": whatsapp.configure(),
            "telephone": whatsapp.masquer_numero(fiche["telephone"]) if fiche.get("telephone") else "",
            "telephone_verifie": bool(fiche.get("telephone_verifie")), "otp_wa_actif": bool(fiche.get("otp_wa_actif")),
            "cles_acces": db.base().passkeys.count_documents({"utilisateur_id": u["id"]}),
            "biometrie_appareil": bool(x_appareil and db.base().biometries.find_one({"utilisateur_id": u["id"], "appareil_id": x_appareil[:64]}))}


@routeur.post("/compte/telephone/demande")
def telephone_demande(corps: dict, fond: BackgroundTasks, u: dict = Depends(auth.utilisateur_courant)):
    """Corps : {telephone}. Envoie un code WhatsApp au numéro pour prouver qu'il est bien à la personne."""
    if not whatsapp.configure():
        raise HTTPException(503, "WhatsApp n'est pas encore activé sur le serveur")
    numero = whatsapp.normaliser_numero(str(corps.get("telephone", "")))
    if not numero:
        raise HTTPException(400, "Numéro invalide (indicatif + numéro, ex. +226 70 12 34 56)")
    if db.base().utilisateurs.find_one({"telephone": numero, "telephone_verifie": True, "id": {"$ne": u["id"]}}):
        raise HTTPException(409, "Ce numéro est déjà utilisé par un autre compte")
    if trop_de_demandes(u):
        raise HTTPException(429, "Trop de demandes : réessayez dans une heure")
    fond.add_task(whatsapp.envoyer_code, numero, creer_code(u, "telephone", numero), "vérification du numéro")
    return {"ok": True, "message": "Code envoyé par WhatsApp"}


@routeur.post("/compte/telephone/verifier")
def telephone_verifier(corps: dict, u: dict = Depends(auth.utilisateur_courant)):
    """Corps : {code}. Si le code est juste, le numéro devient le numéro WhatsApp vérifié du compte."""
    fiche = controler_code(u, "telephone", str(corps.get("code", "")))
    numero = fiche["cible"]
    if db.base().utilisateurs.find_one({"telephone": numero, "telephone_verifie": True, "id": {"$ne": u["id"]}}):
        raise HTTPException(409, "Ce numéro est déjà utilisé par un autre compte")
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": {"telephone": numero, "telephone_verifie": True}})
    auth.journaliser("telephone_verifie", u)
    return {"ok": True, "telephone": whatsapp.masquer_numero(numero)}


@routeur.delete("/compte/telephone")
def telephone_retirer(u: dict = Depends(auth.utilisateur_courant)):
    """Retire le numéro du compte (plus de connexion par WhatsApp, de lien « mot de passe oublié » ni de second facteur WhatsApp)."""
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": {"telephone": "", "telephone_verifie": False, "otp_wa_actif": False}})
    auth.journaliser("telephone_retire", u)
    return {"ok": True}


@routeur.put("/compte/otp-wa")
def otp_wa(corps: dict, u: dict = Depends(auth.utilisateur_courant)):
    """Corps : {actif, mot_de_passe}. Active ou désactive le code WhatsApp demandé EN PLUS du mot de passe (numéro vérifié exigé, mot de passe redemandé)."""
    fiche = db.base().utilisateurs.find_one({"id": u["id"]})
    if not securite.verifier_mot_de_passe(str(corps.get("mot_de_passe", "")), fiche["mot_de_passe_hash"]):
        raise HTTPException(400, "Mot de passe incorrect")
    actif = bool(corps.get("actif"))
    if actif and not fiche.get("telephone_verifie"):
        raise HTTPException(409, "Vérifiez d'abord votre numéro WhatsApp")
    if actif and not whatsapp.configure():
        raise HTTPException(503, "WhatsApp n'est pas encore activé sur le serveur")
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": {"otp_wa_actif": actif}})
    auth.journaliser("otp_wa_active" if actif else "otp_wa_desactive", u)
    return {"ok": True, "otp_wa_actif": actif}


# ---------- 4. empreinte / visage d'un appareil (application Android) ----------

@routeur.post("/compte/biometrie/activer")
def biometrie_activer(u: dict = Depends(auth.utilisateur_courant), x_appareil: str = Header(default="")):
    """
    Crée le secret de CET appareil (renvoyé une seule fois ; le serveur n'en garde que l'empreinte). L'application le range dans son
    coffre chiffré, déverrouillable seulement par l'empreinte / le visage de la personne.
    """
    if not x_appareil.strip():
        raise HTTPException(400, "Appareil non identifié")
    secret = secrets.token_urlsafe(32)
    b = db.base()
    b.biometries.delete_many({"utilisateur_id": u["id"], "appareil_id": x_appareil[:64]})
    b.biometries.insert_one({"id": str(uuid.uuid4()), "utilisateur_id": u["id"], "appareil_id": x_appareil[:64], "hash": _empreinte(secret), "cree": db.maintenant()})
    auth.journaliser("biometrie_activee", u, x_appareil[:64])
    return {"secret": secret}


@routeur.delete("/compte/biometrie")
def biometrie_retirer(u: dict = Depends(auth.utilisateur_courant), x_appareil: str = Header(default="")):
    db.base().biometries.delete_many({"utilisateur_id": u["id"], "appareil_id": x_appareil[:64]})
    auth.journaliser("biometrie_retiree", u, x_appareil[:64])
    return {"ok": True}


@routeur.post("/auth/biometrie")
def biometrie_connexion(corps: dict, x_appareil: str = Header(default="")):
    """
    Corps : {login, secret}. Le secret n'est lisible par l'application qu'après l'empreinte / le visage ; l'appareil enregistré tient lieu de
    second facteur. Compte désactivé, appareil inconnu ou mot de passe changé depuis : refus.
    """
    u = db.base().utilisateurs.find_one({"login": str(corps.get("login", "")).strip().lower()})
    auth.verifier_non_bloque(u)
    fiche = db.base().biometries.find_one({"utilisateur_id": u["id"], "appareil_id": x_appareil[:64]}) if u and x_appareil.strip() else None
    if not u or not u.get("actif", True) or not fiche or not hmac.compare_digest(fiche["hash"], _empreinte(str(corps.get("secret", "")))):
        if u:
            auth.echec_acces(u, "empreinte refusée")
        raise HTTPException(401, "Connexion biométrique expirée : connectez-vous avec votre mot de passe")
    return auth.ouvrir_session(u, controle_2fa=False, moyen="biométrie")
