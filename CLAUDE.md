# Dialyse — règles du dépôt (propriétaire ShuyahBF)

Les règles permanentes du propriétaire (voir le CLAUDE.md de `ShuyahBF/Aizenta-Analyse-Qualit-Gestion-Stocks` ou `ShuyahBF/Emergent`) s'appliquent ici.
Rappel des principales :
- Commits : auteur ET committer `ShuyahBF <jfrancois.ouoba@gmail.com>`, messages et commentaires en français, aucune mention d'IA ni de Co-Authored-By.
- Commentaires clairs sur chaque bloc de code (le propriétaire vient de WinDev). Jamais de secret dans le dépôt (variables d'environnement Render).
- Après chaque livraison : fusion, puis compte rendu dans le chat ET par e-mail HTML à jfrancois.ouoba@gmail.com (`mcp__Gmail__send_message`, `htmlBody`) :
  date et heure, identification (dépôt, branche, commit, version, lot), périmètre, comment vérifier, à activer, points d'attention, reste à faire.
- Version et lot : source unique `backend/lot.py` (VERSION `1.N` +1 et LOT = numéro de la PR fusionnée à chaque déploiement), exposée par `/api/version`.
  Connexion et portail : « Version X · déployée le JJ/MM/AAAA HH:MM » ; pages d'administration : libellé complet avec lot et commit (`BandeauVersion detaille`).
- Tableaux : survol bleu clair `rgba(56,189,248,0.16)`, sélection orange `#f6a35b` police bleu nuit `#0A1E3D`, nombres à droite, TOUTES les colonnes triables
  (▲ ▼ ⇅, vides en dernier), bouton « Actualiser » avec toast « … en cours » puis résultat.
- Pictogramme + légende sur toute action ; enregistrement jamais « deviné » (bouton Enregistrer actif si modifié + mention « modifié, non enregistré »).
- Listes finies = listes déroulantes ; détails d'une ligne = fenêtre modale (28 / 36 rem, 85 % de hauteur) ; œil sur toute saisie secrète ; menus avec majuscule à chaque mot ;
  exemples d'identification locaux (« BADINI Awa », « awa.badini@gmail.com »).
- Chargement : jamais de boucle N+1 (lectures en bloc), appels externes en arrière-plan, index sur les filtres fréquents.
- Présence auprès de SAWALI : signal au démarrage puis toutes les 5 minutes (`presence_sawali` dans `backend/app/main.py`), sans aucune donnée de patient.
- Le propriétaire ne manipule ni Python ni PowerShell : tout outil de maintenance passe par une interface graphique de la plateforme.

## Plateforme
- Dépôt `ShuyahBF/dialyse`, branche de base `main`. Serveur `backend/` (FastAPI + MongoDB, collections `utilisateurs, parametres, journal, patients, postes, seances, historique`),
  site `frontend/` (React, Vite, Tailwind, lucide-react). Déploiement Render par `render.yaml` (deux services : `dialyse-api`, `dialyse-web`).
- Architecture reprise de « Déplacés internes » (comptes, rôles, journal, 2FA, historique des champs modifiés).

## Décisions de conception (lot 1, 17/11/2026)
- **Confidentialité par le serveur** : le secrétariat ne reçoit JAMAIS les champs médicaux ni le détail des séances (`patients.masquer`, `seances._public`) ; le masquage n'est pas fait dans l'écran.
- **Données de santé** : chaque ouverture d'un dossier ou d'une séance est journalisée (`patient_lu`, `seance_lue`) ; l'historique garde les NOMS des champs modifiés, jamais leurs valeurs ;
  aucun secret ni donnée de patient dans les journaux, les signaux ou les e-mails. Écran flouté à la perte du focus, Impr. écran neutralisée, impression bloquée.
- **Pas de suppression de données médicales** : un patient ayant des séances ne se supprime pas (on change son statut) ; un poste ayant des séances passe « hors service » ; une séance validée par le médecin est verrouillée.
- **Planning** : un poste ne reçoit qu'une séance par créneau et un patient qu'une par créneau ; un patient à sérologie positive est placé sur un poste d'isolement (alerte à la planification manuelle, obligation à la génération automatique).
- **Alertes cliniques** (`backend/app/alertes.py`) : fonctions pures, seuils usuels regroupés au même endroit, **à valider par le médecin responsable** ; elles alertent, elles n'interdisent rien.
- **Bilans biologiques (lot 2)** : catalogue, cibles et seuils critiques dans `backend/app/bilans_ref.py` (fonctions pures, **à valider par le médecin responsable**) ; l'interprétation (statuts, URR, alertes) est calculée à la lecture, jamais stockée ;
  données médicales : jamais le secrétariat ni le technicien ; correction réservée au médecin, suppression à l'administration ; bilan « en retard » = dernier bilan de plus de 35 jours.
- Prochains lots : consommables et stocks, facturation et prise en charge, rapports, sauvegardes chiffrées, biométrie et OTP WhatsApp, puis application Android (DG et médecins, dossiers anonymisés).

## Tests avant toute livraison
- `cd backend && python -m pytest tests -q` (base en mémoire `mongomock`).
- `cd frontend && npm test && npm run build`.
