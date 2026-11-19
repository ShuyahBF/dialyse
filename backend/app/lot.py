"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.17"
LOT = "19"
LOT_LIBELLE = "Centre de messagerie WhatsApp (contacts, conversations, documents, rappels, réservations par WhatsApp), calendrier d'activité interactif, réservations, liste d'attente, notifications automatiques du patient (option par centre) et pastilles de notifications du menu."
