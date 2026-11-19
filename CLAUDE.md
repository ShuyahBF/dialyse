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
  WhatsApp passe par la **Transmission WA universelle « Liluvine Standard » de SAWALI** (lot 9, comme toutes les plateformes du propriétaire : jamais de jeton Meta propre) : protocole signé HMAC dans
  `backend/app/whatsapp.py` (un nouvel essai sur 5xx, jamais sur 4xx, 409 = STOP, texte jamais journalisé). Variables Render : `LILUVINE_WA_URL`, `LILUVINE_WA_EMETTEUR` (« dialyse »), `LILUVINE_WA_HMAC` (SECRET : clé de l'émetteur « dialyse » créé dans SAWALI), `FRONTEND_ORIGIN`.
  Sans la clé, les boutons WhatsApp sont masqués.
- **Suivi anonymisé et application Android (lot 11, 17/11/2026)** : `backend/app/anonyme.py` (route `/anonyme`, rôles direction, médecin, administration) ; le serveur ne renvoie JAMAIS nom, prénom, téléphone ni adresse :
  code patient, âge, sexe, statut, alertes. Alertes suivies : valeurs de bilan critiques, alertes de séance (hypotension…), incidents, ruptures de stock, bilans en retard ; identifiants STABLES (une notification par alerte).
  Notifications du téléphone : JETON DE LECTURE (`/anonyme/jeton`, empreinte SHA-256 seule gardée, 5 téléphones au plus, annulé à la désactivation du compte ou au changement de rôle) qui n'ouvre QUE `/anonyme/flux`.
  Application Android `android/` (paquet `com.shuyah.dialyse`, hybride comme auRor) : le site dans une fenêtre intégrée, verrou par empreinte OBLIGATOIRE (refus d'ouverture sans verrouillage d'écran), captures d'écran interdites (FLAG_SECURE),
  notifications par tâche planifiée toutes les 15 min (`Alertes.kt`, jeton chiffré par le coffre Android, texte neutre sur l'écran verrouillé, l'existant est mémorisé sans notifier à l'activation). Pont `window.DialyseAndroid` (`frontend/src/lib/pontAndroid.js`).
  Build : `cd android && gradle :app:assembleRelease -PsignerAvecCleLocale=true` ; livraison : APK `dialyse-X.Y.apk` envoyé au propriétaire et déposé dans ShuyahStore.

- **Dossier d'adhésion (lot 12, 17/11/2026)** : `backend/app/adhesion.py` — MODÈLE de demande = liste des pièces à fournir pour entrer dans la file active d'un centre (modèle par défaut : pièce d'identité CNIB / passeport, bulletin de référence, bilans biologiques récents,
  sérologies hépatites B et C et VIH, échographie rénale, certificat d'indigence facultatif). Chaque centre peut avoir une VARIANTE ou son modèle propre (administration : écran « Modèles de dossier d'adhésion », création, duplication, modification, modèle par défaut) ;
  chaque patient est rattaché à un modèle (défaut sinon). On note seulement la RÉCEPTION de chaque pièce (reçue / manquante / sans objet pour une pièce facultative), jamais son contenu : le secrétariat tient la liste sans voir de donnée médicale.
  Les clés de pièces sont stables (renommer ne perd pas l'état) ; un modèle utilisé ou par défaut ne se supprime pas ; dossier complet = toutes les pièces OBLIGATOIRES reçues ; filtre « dossiers incomplets » dans la liste des patients.

## Charte graphique (lot 8, 17/11/2026 : « applique les styles, typographies et présentations de ZandGo »)
- Reprise de ZandGo : couleurs `encre` #0A1E3D (barre latérale, bandeaux), `emeraude` #03316E (actions), `citron` #FF7A0A (élément actif, accent), `brume` #F3F5F9 (fond), `ardoise` #56627A ; Montserrat partout, Playfair Display italique
  (`font-editorial`) pour les titres de bandeau ; thème CLAIR imposé ; barre latérale de 230 px, boutons en pilule, champs bleu clair arrondis, cartes `rounded-2xl ring-1 ring-encre/5`, connexion sur fond bleu nuit.
- Les anciens noms `nuit` et `turquoise` du code pointent vers ces couleurs (`frontend/tailwind.config.js`). Logo : `composants/Logo.jsx` (goutte et pouls, « Dia » / « lyse »).

## Tests avant toute livraison
- `cd backend && python -m pytest tests -q` (base en mémoire `mongomock`).
- `cd frontend && npm test && npm run build`.

## Tableaux de plus de 30 lignes : barre de défilement (règle 24, 18/11/2026 : « C'est une règle à considérer partout sur toutes les plateformes »)
- Tout tableau qui présente PLUS DE 30 LIGNES défile dans son cadre (hauteur = 30 lignes + l'en-tête) au lieu d'allonger la page ; l'en-tête reste visible en haut pendant le défilement ;
  à l'impression, toutes les lignes sortent. Exception possible : `<table data-sans-defilement>`.
- Mise en œuvre ici : module global `frontend/src/lib/defilementTableaux.js` installé au démarrage du site (règles CSS dans `index.css`) : rien à ajouter tableau par tableau.

## Compte rendu par e-mail AUTOMATIQUE après toute livraison (règle du propriétaire, 19/11/2026 : « L'envoi de l'e-mail doit être automatique »)
- L'e-mail HTML à jfrancois.ouoba@gmail.com (outil Gmail, voir règle 12) part TOUT SEUL à la fin de CHAQUE livraison, sans que le
  propriétaire ait à le demander ni à le rappeler, et sans demander confirmation avant l'envoi.
- « Livraison » = tout ce qui atteint le propriétaire ou les utilisateurs, même sans fusion ni déploiement Render : dépôt d'un APK ou d'une
  nouvelle version dans ShuyahStore, publication d'une version, correction, changement de libellé, simple règle ajoutée au CLAUDE.md, fichier
  envoyé au propriétaire. Aucune exception de taille.
- Ne pas conclure « la règle ne s'applique pas, rien n'a été déployé sur Render » : en cas de doute, envoyer l'e-mail.
- Contenu : date et heure, identification (dépôt, branche, commit, version, lot), périmètre, comment vérifier, à activer, points
  d'attention, reste à faire. Jamais de secret (clé, mot de passe, chaîne de connexion) dans l'e-mail.
- Charger l'outil Gmail avec ToolSearch AVANT de dire qu'il manque ; s'il est vraiment indisponible, le dire dans le chat et ne pas clore la livraison.

## Multi-centres (lot 15, propriétaire, 19/11/2026 : « multi centre de dialyse… on s'inspirera de eKol : chaque centre a ses patients, examens, utilisateurs, etc. »)
- **Principe** : un centre = un « locataire ». Collection `centres` (id, nom, préfixe, ville, téléphone, actif) ; TOUTE donnée de travail porte `centre_id` : patients, postes, séances, bilans, articles, lots, mouvements, tarifs, organismes, factures,
  modèles d'adhésion, historique, paramètres (compteurs, en-tête de la clinique) et journal. Les comptes (`utilisateurs`) ont un `centre_id`.
- **Filtrage automatique et refus par défaut** (`backend/app/db.py`) : `db.base()` renvoie la vue du centre courant ; les collections de `COLLECTIONS_CENTRE` sont filtrées sur `centre_id` en lecture, modification, suppression et marquées à l'écriture. Sans centre courant : erreur 400
  (jamais « tout »). Un écran ne peut donc pas « oublier » de filtrer. `db.brut()` (sans filtre) est réservé à la migration, aux sauvegardes (tous centres, super administrateur) et aux listes de centres : toute nouvelle utilisation doit avoir une raison écrite.
  Toute NOUVELLE collection de données de centre est ajoutée à `COLLECTIONS_CENTRE` (et son index unique devient « par centre »).
- **Centre de la requête** (`auth.utilisateur_courant`, dépendance ASYNCHRONE exprès : la variable de contexte doit être posée dans la tâche de la requête) : un compte rattaché à un centre travaille TOUJOURS dans le sien (l'en-tête `X-Centre` est ignoré : aucun passage d'un centre à l'autre) ;
  un compte du GROUPE (super administrateur, ou direction sans centre : `roles.ROLES_GROUPE`) choisit son centre par `X-Centre` (sinon 400 « Choisissez d'abord un centre ») ; un centre désactivé ferme l'accès de ses comptes (le super administrateur reste admis).
- **Comptes** : un administrateur ne voit et ne crée que les comptes de SON centre (un compte d'un autre centre est « introuvable ») ; le super administrateur crée les centres (`POST /centres`) et choisit le centre d'un nouveau compte ; identifiants (`login`) uniques sur toute la plateforme.
- **Codes et numéros par centre** : codes patients `<préfixe>-000001` (compteur par centre ; le préfixe ne change plus après le premier patient) ; numérotation des factures, noms d'articles et modèle « defaut » uniques DANS un centre (anciens index uniques retirés au démarrage par `creer_index`).
- **Migration** (`centres.amorcer_centre_initial`, idempotente, à chaque démarrage et après une restauration) : « Centre principal » (préfixe DIAL) reprend toutes les données d'avant ; les comptes du groupe restent sans centre.
- **Notifications du téléphone** : le jeton de lecture porte le centre ; le flux ne couvre que ce centre. **Sauvegardes** : base complète (tous les centres), super administrateur seul, comme avant.
- Écran : barre latérale « Centre » (nom imposé, ou liste déroulante pour le groupe), page « Centres De Dialyse » (super administrateur), colonne et liste « Centre » dans « Gestion Des Comptes ». Tests : `backend/tests/test_multi_centres.py`.
- **À venir** : rapports consolidés de tous les centres pour le directeur général et le super administrateur ; administrateur multi-centres ; transfert d'un patient d'un centre à l'autre.

## Fiche du centre : logo, responsable, géolocalisation, papiers à en-tête (lot 17, propriétaire, 19/11/2026)
- Champs de la fiche (collection `centres`, `backend/app/centres.py`) : responsable et sa fonction, adresse, ville, téléphone, e-mail, IFU / RCCM, latitude / longitude (ensemble ou vides, bornes contrôlées), logo.
  Le super administrateur tient tout (« Centres De Dialyse ») ; l'administrateur du centre tient la fiche de SON centre (« Fiche Du Centre », `PUT /centre`) sauf nom, préfixe et état.
- Logo : reçu en data URL, VÉRIFIÉ avec Pillow (PNG, JPEG ou WebP réels, 600 Ko au plus), réduit à 480 px et ré-encodé en PNG (métadonnées retirées) ; jamais dans les listes (`a_logo` seulement), joint à `GET /centre` et `GET /centres/{id}`.
- En-tête des papiers : `centres.entete_courant()` (fiche du centre, complétée par l'ancien en-tête des factures de `parametres`) ; logo et responsable sur les PDF de factures et de rapports ; `GET /centre/papier-entete?format=A4|A5` = papier vierge (logo, nom, responsable, coordonnées, filet orange, pied avec IFU / adresse / position GPS), affiché dans le lecteur interne.
- Écran : `composants/FicheCentre.jsx` (logo avec aperçu, géolocalisation « Utiliser ma position » + lien carte OpenStreetMap), `pages/FicheCentre.jsx`. Tests : `backend/tests/test_multi_centres.py`.

## Nom de domaine (propriétaire, 19/11/2026)
- Site : `https://looisdialyse.space` ; API : `https://api.looisdialyse.space` (déclarés dans `render.yaml`, `domains`). Les anciennes adresses onrender.com ne sont plus utilisées. Aucune clé d'accès n'existait : on repart de zéro (`FRONTEND_ORIGIN` = `https://looisdialyse.space`).
