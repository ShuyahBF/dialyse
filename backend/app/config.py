"""
Configuration lue UNIQUEMENT dans les variables d'environnement (jamais de secret dans le code).
Sur Render : onglet « Environment » du service.

  MONGODB_URI              chaîne de connexion Atlas (secret, saisie par le propriétaire)
  MONGODB_BASE             nom de la base (défaut « dialyse »)
  JWT_SECRET               longue phrase secrète aléatoire (secret)
  SUPERADMIN_LOGIN         identifiant du premier super administrateur (créé au 1er démarrage)
  SUPERADMIN_MOT_DE_PASSE  son mot de passe initial (secret ; à changer à la 1re connexion)
  SAUVEGARDE_CLE           clé de chiffrement des sauvegardes (16 caractères minimum, secret saisi par le propriétaire ; à garder en lieu sûr)
  TACHES_DE_FOND           « 0 » pour désactiver les tâches planifiées (tests)
  WEBAUTHN_RP_ID           nom de domaine du site pour les clés d'accès (défaut : domaine de FRONTEND_ORIGIN) ; le changer oblige à recréer les clés
  LILUVINE_WA_URL / LILUVINE_WA_HMAC / LILUVINE_WA_EMETTEUR  WhatsApp par « Liluvine Standard » de SAWALI (la clé HMAC est un secret saisi dans Render)
  FRONTEND_ORIGIN          adresse du site web (pour CORS), https://looisdialyse.cloud
  PRESENCE_SAWALI          « 0 » pour désactiver le signal de présence (tests)
"""
import os


def env(nom: str, defaut: str = "") -> str:
    """Valeur d'une variable d'environnement (chaîne vide si absente)."""
    return os.environ.get(nom, defaut)


DUREE_JETON_HEURES = 10          # un jeton de connexion vaut 10 heures (une journée de travail)
TENTATIVES_MAX = 5               # 5 mots de passe faux de suite = compte bloqué un moment
BLOCAGE_MINUTES = 15             # durée du blocage


def origines_site() -> list[str]:
    """Adresses autorisées du site web (FRONTEND_ORIGIN, séparées par des virgules), sans « / » final."""
    return [o.strip().rstrip("/") for o in env("FRONTEND_ORIGIN").split(",") if o.strip()]


def rp_id() -> str:
    """Identifiant WebAuthn : domaine du site (WEBAUTHN_RP_ID, ou domaine de la première adresse de FRONTEND_ORIGIN)."""
    from urllib.parse import urlparse
    return env("WEBAUTHN_RP_ID") or (urlparse(origines_site()[0]).hostname if origines_site() else "") or "localhost"
