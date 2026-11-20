"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.25"
LOT = "28"
LOT_LIBELLE = "Prévisions de rupture et bon de commande : quand chaque consommable va manquer, quoi commander pour 15 à 90 jours, bon de commande PDF sur le papier à en-tête."
