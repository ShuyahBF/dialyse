"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.20"
LOT = "23"
LOT_LIBELLE = "Correctif messagerie WhatsApp : la zone d'écriture d'un message ne se vide plus et la jauge ne tourne plus sans fin ; menu « Centre De Messagerie WA »."
