"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.16"
LOT = "18"
LOT_LIBELLE = "Centre de travail en haut de chaque écran ; synthèse consolidée de tous les centres (direction et super administrateur) ; transfert d'un patient d'un centre à l'autre."
