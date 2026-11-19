"""
SOURCE UNIQUE de la version et du lot du serveur (règles du propriétaire n° 1 et 2).

À CHAQUE déploiement : augmenter VERSION (compteur « 1.N ») et mettre LOT = numéro de la PR fusionnée.
Modifier ce fichier force aussi le redéploiement sur Render (le service a un rootDir « backend »).
La date de déploiement est celle du démarrage du serveur (voir main.py).
"""
VERSION = "1.15"
LOT = "17"
LOT_LIBELLE = "Fiche du centre : logo, nom du responsable, coordonnées, géolocalisation, papiers à en-tête A4 et A5 ; logo et responsable sur les factures et les rapports."
