"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.22"
LOT = "25"
LOT_LIBELLE = "Fond de la page d'accueil : image ou vidéo choisie par le super administrateur (Apparence De L'Accueil), avec aperçu et assombrissement réglable."
