"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.14"
LOT = "15"
LOT_LIBELLE = "Multi-centres (modèle e-Kol) : chaque centre a ses patients, postes, séances, stocks, factures et comptes ; centres créés par le super administrateur ; choix du centre pour les comptes du groupe."
