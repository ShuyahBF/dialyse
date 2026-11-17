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
- **Consommables et stocks (lot 3)** : stock = somme des LOTS (numéro obligatoire à l'entrée : traçabilité) ; sorties en FEFO hors lots périmés ; le démarrage d'une séance décompte les articles « par séance » et note les lots
  utilisés ; un stock insuffisant ne bloque JAMAIS un soin (le manque est noté sur la séance et dans les alertes) ; rappel de lot : `GET /stock/tracabilite` (soignants et administration, consultation journalisée).
- **Facturation (lot 4)** : montants en FCFA ENTIERS ; une facture par séance TERMINÉE, prix / noms / taux COPIÉS à l'émission (une facture émise ne change plus) ; part organisme arrondie, part patient = complément ;
  taux du patient > taux de l'organisme > 0 % ; paiements partiels du patient ou de l'organisme, jamais au-delà du reste dû ; une facture ne se supprime pas : elle s'ANNULE (administration, motif, aucun paiement) ;
  PDF `reportlab` servi en `inline` et affiché dans le lecteur interne (`PdfInterne`, seules actions « Imprimer » et « Fermer », aucun téléchargement) ; aucune donnée médicale sur une facture ;
  tarifs, organismes et en-tête : administration ; caisse : secrétariat et administration (le médecin n'y a pas accès).
- **Rapports (lot 5)** : AGRÉGÉS, jamais de nom ni de code patient (test `test_droits_direction_anonymat_et_journal`) ; calculs purs dans `backend/app/rapports.py` ; âge calculé à la date de chaque séance ; période libre de 366 jours au plus ;
  consultation journalisée ; PDF `inline` dans le lecteur interne. Rôle **Directeur général** (`direction`) : rapports et tableau de bord agrégés seulement (le serveur lui refuse patients, séances, bilans, stock, factures, comptes, journal).
- **Sauvegardes (lot 6)** : gzip + Fernet, clé `SAUVEGARDE_CLE` (Render, 16 caractères minimum, jamais dans le dépôt) ; une sauvegarde n'est comptée que si elle a été RELUE (« intacte » : empreinte + déchiffrement + compteurs) ;
  restauration = aperçu, confirmation « RESTAURER », copie de sécurité vérifiée AVANT, contrôle des compteurs APRÈS, retour arrière automatique au moindre écart ; le journal d'audit n'est jamais remplacé ;
  restauration refusée si le compte du super administrateur n'est pas dans la sauvegarde ; restaurer, télécharger, importer, supprimer : super administrateur seul ; sauvegarde quotidienne dès 02 h UTC (14 gardées).
  Leçon d'une perte de données réelle sur une autre plateforme : ne JAMAIS restaurer sans copie de sécurité ni contrôle après coup.
- **Accès biométrique et WhatsApp (lot 7)** : clés d'accès WebAuthn (`passkeys.py`, vérification de l'utilisateur EXIGÉE, défi à usage unique de 5 min, compteur anti-clonage, lien au domaine `WEBAUTHN_RP_ID` / `FRONTEND_ORIGIN`) ;
  empreinte d'appareil Android (secret par appareil, `/compte/biometrie/*`, `/auth/biometrie`) ; code WhatsApp = connexion, second facteur facultatif, vérification du numéro et lien « mot de passe oublié » (`acces.py`).
  Sécurité : réponses identiques que le compte existe ou non, codes hachés (HMAC), 5 essais par code, 5 demandes par heure et par compte (compteur à part : `envois_acces`), blocage du compte comme pour le mot de passe,
  clés d'accès et empreintes ANNULÉES après une réinitialisation du mot de passe ; clé d'accès ou empreinte = authentification forte (pas de second code) ; messages WhatsApp en fil séparé (jamais dans la requête), sans aucune donnée de patient.
  Variables Render : `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_OTP_TEMPLATE`, `WHATSAPP_RESET_TEMPLATE`, `FRONTEND_ORIGIN`. Sans elles, les boutons WhatsApp sont masqués.
- Prochains lots : application Android (DG et médecins, dossiers anonymisés).

## Tests avant toute livraison
- `cd backend && python -m pytest tests -q` (base en mémoire `mongomock`).
- `cd frontend && npm test && npm run build`.
