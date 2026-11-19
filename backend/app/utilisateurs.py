"""Comptes : connexion, profil, changement de mot de passe, gestion par l'administration (création, rôle, activation, réinitialisation)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from . import auth, db, roles, securite, validation
from .auth import exiger_roles, journaliser, utilisateur_courant

routeur = APIRouter()


def _public(u: dict) -> dict:
    """Compte sans secret (jamais de hachage, de secret 2FA ni de compteur d'échecs)."""
    return {"id": u["id"], "login": u["login"], "nom_affiche": u.get("nom_affiche", ""), "role": u["role"],
            "role_libelle": roles.LIBELLES.get(u["role"], u["role"]), "actif": u.get("actif", True),
            "totp_actif": bool(u.get("totp_actif")), "doit_changer_mdp": bool(u.get("doit_changer_mdp")),
            "created_at": u.get("created_at", ""), "centre_id": u.get("centre_id"), "centre_nom": u.get("_centre_nom", "")}


@routeur.post("/auth/login")
def login(corps: dict):
    """Connexion. Corps : {login, mot_de_passe, code_2fa?}."""
    return auth.connexion(str(corps.get("login", "")), str(corps.get("mot_de_passe", "")), str(corps.get("code_2fa", "")))


@routeur.get("/me")
def moi(u: dict = Depends(utilisateur_courant)):
    return {**u, "role_libelle": roles.LIBELLES.get(u["role"], u["role"])}


@routeur.post("/auth/changer-mot-de-passe")
def changer_mot_de_passe(corps: dict, u: dict = Depends(utilisateur_courant)):
    """Le compte change lui-même son mot de passe (ancien mot de passe exigé)."""
    fiche = db.base().utilisateurs.find_one({"id": u["id"]})
    if not securite.verifier_mot_de_passe(str(corps.get("ancien", "")), fiche["mot_de_passe_hash"]):
        raise HTTPException(400, "Ancien mot de passe incorrect")
    nouveau = str(corps.get("nouveau", ""))
    if not securite.mot_de_passe_assez_fort(nouveau):
        raise HTTPException(400, "Mot de passe trop faible : 8 caractères au moins, avec une lettre et un chiffre")
    db.base().utilisateurs.update_one({"id": u["id"]}, {"$set": {"mot_de_passe_hash": securite.hacher_mot_de_passe(nouveau), "doit_changer_mdp": False}})
    journaliser("mot_de_passe_change", u)
    return {"ok": True}


def _roles_autorises(u: dict) -> set:
    """Rôles que ce compte a le droit de créer ou de modifier."""
    return set(roles.TOUS_LES_ROLES) if u["role"] == roles.SUPER_ADMIN else roles.ROLES_GERES_PAR_ADMIN


def _noms_centres() -> dict:
    """Identifiant → nom de chaque centre (une seule lecture pour toute la liste)."""
    return {c["id"]: c["nom"] for c in db.brut().centres.find({}, {"_id": 0, "id": 1, "nom": 1})}


def _filtre_centre(u: dict) -> dict:
    """Comptes visibles : ceux du centre de travail (un administrateur n'en a pas d'autre) ; un compte du groupe sans centre choisi voit tout."""
    return {"centre_id": u["centre_id"]} if u["centre_id"] else {}


@routeur.get("/utilisateurs")
def lister(u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Comptes (sans secret), par identifiant : ceux du centre de travail ; le super administrateur sans centre choisi les voit tous, avec leur centre."""
    noms = _noms_centres()
    return [_public({**x, "_centre_nom": noms.get(x.get("centre_id"), "Groupe" if not x.get("centre_id") else "")})
            for x in db.brut().utilisateurs.find(_filtre_centre(u), {"_id": 0}).sort("login", 1)]


@routeur.get("/roles")
def liste_roles(u: dict = Depends(utilisateur_courant)):
    """Liste finie des rôles que ce compte peut attribuer (liste déroulante)."""
    ok = _roles_autorises(u) if u["role"] in roles.ADMINISTRATION else set()
    return [{"valeur": r, "libelle": roles.LIBELLES[r]} for r in roles.TOUS_LES_ROLES if r in ok]


def _centre_du_nouveau_compte(corps: dict, u: dict, role: str):
    """
    Centre de rattachement d'un nouveau compte. Un administrateur crée toujours dans SON centre. Le super administrateur peut désigner un
    centre (`centre_id`), sinon c'est le centre où il travaille ; un compte du groupe (super administrateur, direction) peut n'avoir AUCUN
    centre (`centre_id` vide). Tout autre rôle doit avoir un centre.
    """
    if u["role"] != roles.SUPER_ADMIN:
        return u["centre_id"]
    if "centre_id" in corps:
        voulu = str(corps.get("centre_id") or "").strip()
    else:
        voulu = u["centre_id"] or ""
    if not voulu:
        if role in roles.ROLES_GROUPE:
            return None
        validation.erreur("Choisissez le centre de ce compte")
    if not db.brut().centres.find_one({"id": voulu}):
        validation.erreur("Centre inconnu")
    return voulu


@routeur.post("/utilisateurs")
def creer(corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Crée un compte (mot de passe provisoire à changer à la première connexion)."""
    login_ = validation.texte(corps, "login", "Identifiant", True, 40).lower()
    if not login_.replace(".", "").replace("-", "").replace("_", "").isalnum():
        validation.erreur("Identifiant : lettres, chiffres, point, tiret et souligné seulement")
    role = validation.choix(corps, "role", "Rôle", roles.TOUS_LES_ROLES, obligatoire=True)
    if role not in _roles_autorises(u):
        raise HTTPException(403, "Vous ne pouvez pas créer un compte avec ce rôle")
    mdp = str(corps.get("mot_de_passe", ""))
    if not securite.mot_de_passe_assez_fort(mdp):
        validation.erreur("Mot de passe provisoire trop faible : 8 caractères au moins, avec une lettre et un chiffre")
    if db.base().utilisateurs.find_one({"login": login_}):
        raise HTTPException(409, "Cet identifiant existe déjà")
    centre_id = _centre_du_nouveau_compte(corps, u, role)
    doc = {"id": str(uuid.uuid4()), "login": login_, "nom_affiche": validation.texte(corps, "nom_affiche", "Nom affiché", True, 80),
           "role": role, "actif": True, "echecs": 0, "mot_de_passe_hash": securite.hacher_mot_de_passe(mdp),
           "doit_changer_mdp": True, "created_at": db.maintenant(), "cree_par": u["login"], "centre_id": centre_id}
    db.base().utilisateurs.insert_one(doc)
    journaliser("compte_cree", u, f"{login_} ({role})")
    return _public(doc)


def _cible(id_: str, u: dict) -> dict:
    """Compte visé, avec contrôle du droit de le gérer (un admin ne touche ni aux admins ni au super administrateur)."""
    c = db.base().utilisateurs.find_one({"id": id_, **_filtre_centre(u)})            # un compte d'un autre centre est « introuvable »
    if not c:
        raise HTTPException(404, "Compte introuvable")
    if c["role"] not in _roles_autorises(u) and c["id"] != u["id"]:
        raise HTTPException(403, "Vous ne pouvez pas gérer ce compte")
    return c


@routeur.put("/utilisateurs/{id_}")
def modifier(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Modifie le nom affiché, le rôle ou l'état actif d'un compte. On ne se désactive pas soi-même."""
    c = _cible(id_, u)
    maj: dict = {}
    if "nom_affiche" in corps:
        maj["nom_affiche"] = validation.texte(corps, "nom_affiche", "Nom affiché", True, 80)
    if "role" in corps and corps["role"] != c["role"]:
        if c["id"] == u["id"]:
            raise HTTPException(400, "Vous ne pouvez pas changer votre propre rôle")
        r = validation.choix(corps, "role", "Rôle", roles.TOUS_LES_ROLES, obligatoire=True)
        if r not in _roles_autorises(u):
            raise HTTPException(403, "Vous ne pouvez pas attribuer ce rôle")
        maj["role"] = r
    if "actif" in corps:
        if c["id"] == u["id"] and not corps["actif"]:
            raise HTTPException(400, "Vous ne pouvez pas désactiver votre propre compte")
        maj["actif"] = bool(corps["actif"])
    if maj:
        db.base().utilisateurs.update_one({"id": id_}, {"$set": maj})
        journaliser("compte_modifie", u, f"{c['login']} : {', '.join(sorted(maj))}")
    return _public(db.base().utilisateurs.find_one({"id": id_}))


@routeur.post("/utilisateurs/{id_}/reinitialiser")
def reinitialiser(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Nouveau mot de passe provisoire (à changer à la connexion) ; lève le blocage et retire la double authentification."""
    c = _cible(id_, u)
    mdp = str(corps.get("mot_de_passe", ""))
    if not securite.mot_de_passe_assez_fort(mdp):
        validation.erreur("Mot de passe provisoire trop faible : 8 caractères au moins, avec une lettre et un chiffre")
    db.base().utilisateurs.update_one({"id": id_}, {"$set": {"mot_de_passe_hash": securite.hacher_mot_de_passe(mdp), "doit_changer_mdp": True,
                                                           "echecs": 0, "bloque_jusqua": None, "totp_actif": False},
                                                  "$unset": {"totp_secret": ""}})
    journaliser("mot_de_passe_reinitialise", u, c["login"])
    return {"ok": True}


@routeur.get("/journal")
def journal(action: str = "", acteur: str = "", limite: int = 300, u: dict = Depends(exiger_roles(roles.LECTURE_JOURNAL))):
    """Journal d'audit (qui a fait quoi, quand) : les plus récentes lignes d'abord, filtrable. Consultation elle-même non journalisée (bruit)."""
    filtre: dict = dict(_filtre_centre(u))                          # journal du centre de travail (tout le journal pour le groupe sans centre choisi)
    if action:
        filtre["action"] = action
    if acteur:
        filtre["acteur"] = acteur.lower()
    lignes = list(db.base().journal.find(filtre, {"_id": 0}).sort("quand", -1).limit(max(1, min(limite, 1000))))
    return lignes
