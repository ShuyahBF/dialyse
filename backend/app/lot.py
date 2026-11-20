"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.23"
LOT = "26"
LOT_LIBELLE = "Administrateur multi-centres : le super administrateur donne à un administrateur l'accès à plusieurs centres ; il choisit son centre en haut de l'écran."
