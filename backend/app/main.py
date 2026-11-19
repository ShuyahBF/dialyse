"""Serveur « Dialyse » — point d'entrée FastAPI (déployé sur Render)."""
from __future__ import annotations

import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth, db, lot, roles, securite
from .acces import routeur as routeur_acces
from .adhesion import routeur as routeur_adhesion
from .anonyme import routeur as routeur_anonyme
from .passkeys import routeur as routeur_passkeys
from .config import env
from .bilans import routeur as routeur_bilans
from .centres import amorcer_centre_initial, routeur as routeur_centres
from .deuxfacteurs import routeur as routeur_2fa
from .facturation import routeur as routeur_facturation
from .groupe import routeur as routeur_groupe
from .messagerie import routeur as routeur_messagerie
from .activite import routeur as routeur_activite
from .aujourdhui import routeur as routeur_aujourdhui
from .notifications import routeur as routeur_notifications
from .historique import routeur as routeur_historique
from .patients import routeur as routeur_patients
from .postes import routeur as routeur_postes
from .rapports import routeur as routeur_rapports
from .sauvegardes import routeur as routeur_sauvegardes
from .seances import routeur as routeur_seances
from .stock import routeur as routeur_stock
from .tableau import routeur as routeur_tableau
from .utilisateurs import routeur as routeur_utilisateurs

DEPLOYE_LE = datetime.now().strftime("%d/%m/%Y %H:%M")      # date de démarrage = date de déploiement (règle 2)


@asynccontextmanager
async def cycle_de_vie(_app):
    """Au démarrage : signal de présence SAWALI (arrière-plan) et création du premier super administrateur."""
    demarrage()
    yield


app = FastAPI(title="Dialyse", version=lot.VERSION, lifespan=cycle_de_vie)
# CORS : seul le site web de la clinique (FRONTEND_ORIGIN) peut appeler l'API depuis un navigateur.
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in env("FRONTEND_ORIGIN").split(",") if o.strip()],
                   allow_methods=["*"], allow_headers=["*"])
for _r in (routeur_aujourdhui, routeur_activite, routeur_notifications, routeur_messagerie, routeur_groupe, routeur_centres, routeur_utilisateurs, routeur_acces, routeur_adhesion, routeur_anonyme, routeur_passkeys, routeur_2fa, routeur_patients, routeur_postes, routeur_seances, routeur_bilans, routeur_stock, routeur_facturation, routeur_rapports, routeur_sauvegardes, routeur_tableau, routeur_historique):
    app.include_router(_r)


@app.get("/api/version")
def version():
    """Version, lot et date de déploiement (page de connexion et administration)."""
    return {"version": lot.VERSION, "lot": lot.LOT, "lot_libelle": lot.LOT_LIBELLE, "deploye_le": DEPLOYE_LE}


@app.get("/api/sante")
def sante():
    """État du serveur pour la page de connexion (« Serveur actif » / base injoignable)."""
    try:
        db.base().command("ping")
        return {"serveur": "actif", "base": "ok"}
    except Exception:
        return {"serveur": "actif", "base": "injoignable"}


def amorcer_super_admin() -> None:
    """
    Crée le premier super administrateur depuis les variables d'environnement si la base n'a aucun compte.
    RÉCUPÉRATION (mot de passe perdu) : sur Render, définir SUPERADMIN_REINITIALISER=oui avec SUPERADMIN_LOGIN et
    SUPERADMIN_MOT_DE_PASSE : au redémarrage, ce compte reçoit CE mot de passe (à changer à la connexion), son blocage et sa
    double authentification sont levés. Ensuite, supprimer SUPERADMIN_REINITIALISER.
    """
    login, mdp = env("SUPERADMIN_LOGIN").strip().lower(), env("SUPERADMIN_MOT_DE_PASSE")
    if not (login and mdp):
        return
    b = db.base()
    if b.utilisateurs.count_documents({}) == 0:
        b.utilisateurs.insert_one({"id": str(uuid.uuid4()), "login": login, "nom_affiche": "Super administrateur", "role": roles.SUPER_ADMIN,
                                   "actif": True, "echecs": 0, "mot_de_passe_hash": securite.hacher_mot_de_passe(mdp),
                                   "doit_changer_mdp": True, "created_at": db.maintenant(), "centre_id": None})
    elif env("SUPERADMIN_REINITIALISER").strip().lower() in ("oui", "1", "true"):
        fiche = b.utilisateurs.find_one({"login": login, "role": roles.SUPER_ADMIN})
        if fiche:
            b.utilisateurs.update_one({"id": fiche["id"]}, {"$set": {"mot_de_passe_hash": securite.hacher_mot_de_passe(mdp), "doit_changer_mdp": True,
                                                                    "actif": True, "echecs": 0, "bloque_jusqua": None, "totp_actif": False}})
            auth.journaliser("recuperation_super_admin", {"id": fiche["id"], "login": login, "role": roles.SUPER_ADMIN}, "mot de passe réinitialisé au démarrage")


def presence_sawali() -> None:
    """
    Règle 4 du propriétaire : le serveur déclare sa présence à SAWALI au démarrage puis toutes les 5 minutes.
    En arrière-plan, jamais bloquant, aucun secret ni donnée de patient dans le signal.
    """
    import json
    import socket
    import urllib.request
    while True:
        try:
            corps = json.dumps({"application": "Dialyse (serveur)", "version": lot.VERSION, "deploye_le": DEPLOYE_LE,
                                "machine": socket.gethostname(), "systeme": "Render"}).encode()
            req = urllib.request.Request("https://api.sawalismartsystems.com/api/presence-logiciel", data=corps,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass                                   # SAWALI injoignable : on réessaie dans 5 minutes
        time.sleep(300)


def taches_de_fond() -> None:
    """Sauvegarde chiffrée quotidienne (dès 02h00 UTC), vérifiée toutes les 10 minutes. Une panne n'arrête jamais la boucle."""
    from .sauvegardes import sauvegarde_automatique
    while True:
        try:
            sauvegarde_automatique()
        except Exception as e:
            print("Sauvegarde automatique en échec :", e)
        time.sleep(600)


def rappels_en_boucle() -> None:
    """Rappels WhatsApp « X heures avant la séance » (option par centre) : vérifiés toutes les 5 minutes. Une panne n'arrête jamais la boucle."""
    from .messagerie import rappels_automatiques
    while True:
        try:
            rappels_automatiques()
        except Exception as e:
            print("Rappels automatiques en échec :", type(e).__name__)
        time.sleep(300)


def demarrage() -> None:
    if env("PRESENCE_SAWALI", "1") != "0":
        threading.Thread(target=presence_sawali, daemon=True).start()
    if env("TACHES_DE_FOND", "1") != "0":
        threading.Thread(target=taches_de_fond, daemon=True).start()
        threading.Thread(target=rappels_en_boucle, daemon=True).start()
    try:
        amorcer_centre_initial()                   # reprise des données d'avant le multi-centres (idempotent)
        amorcer_super_admin()
    except Exception as e:                         # base injoignable au démarrage : l'API répondra « base injoignable »
        print("Amorçage impossible :", e)
