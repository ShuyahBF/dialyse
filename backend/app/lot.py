"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.7"
LOT = "7"
LOT_LIBELLE = "Accès biométrique (clés d'accès, empreinte d'appareil) et codes WhatsApp : connexion, second facteur, mot de passe oublié"
