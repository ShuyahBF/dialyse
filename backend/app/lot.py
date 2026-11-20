"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.21"
LOT = "24"
LOT_LIBELLE = "Ligne WhatsApp dédiée par centre : chaque centre peut avoir son propre émetteur Liluvine et sa clé ; retours routés vers le bon centre ; repli facultatif sur la ligne partagée."
