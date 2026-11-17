"""
Configuration lue UNIQUEMENT dans les variables d'environnement (jamais de secret dans le code).
Sur Render : onglet « Environment » du service.

  MONGODB_URI              chaîne de connexion Atlas (secret, saisie par le propriétaire)
  MONGODB_BASE             nom de la base (défaut « dialyse »)
  JWT_SECRET               longue phrase secrète aléatoire (secret)
  SUPERADMIN_LOGIN         identifiant du premier super administrateur (créé au 1er démarrage)
  SUPERADMIN_MOT_DE_PASSE  son mot de passe initial (secret ; à changer à la 1re connexion)
  FRONTEND_ORIGIN          adresse du site web (pour CORS), ex. https://dialyse.onrender.com
  PRESENCE_SAWALI          « 0 » pour désactiver le signal de présence (tests)
"""
import os


def env(nom: str, defaut: str = "") -> str:
    """Valeur d'une variable d'environnement (chaîne vide si absente)."""
    return os.environ.get(nom, defaut)


DUREE_JETON_HEURES = 10          # un jeton de connexion vaut 10 heures (une journée de travail)
TENTATIVES_MAX = 5               # 5 mots de passe faux de suite = compte bloqué un moment
BLOCAGE_MINUTES = 15             # durée du blocage
