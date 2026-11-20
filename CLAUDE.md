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
- **Administrateur multi-centres** : voir « Administrateur multi-centres (lot 26) » plus bas.

## Fiche du centre : logo, responsable, géolocalisation, papiers à en-tête (lot 17, propriétaire, 19/11/2026)
- Champs de la fiche (collection `centres`, `backend/app/centres.py`) : responsable et sa fonction, adresse, ville, téléphone, e-mail, IFU / RCCM, latitude / longitude (ensemble ou vides, bornes contrôlées), logo.
  Le super administrateur tient tout (« Centres De Dialyse ») ; l'administrateur du centre tient la fiche de SON centre (« Fiche Du Centre », `PUT /centre`) sauf nom, préfixe et état.
- Logo : reçu en data URL, VÉRIFIÉ avec Pillow (PNG, JPEG ou WebP réels, 600 Ko au plus), réduit à 480 px et ré-encodé en PNG (métadonnées retirées) ; jamais dans les listes (`a_logo` seulement), joint à `GET /centre` et `GET /centres/{id}`.
- En-tête des papiers : `centres.entete_courant()` (fiche du centre, complétée par l'ancien en-tête des factures de `parametres`) ; logo et responsable sur les PDF de factures et de rapports ; `GET /centre/papier-entete?format=A4|A5` = papier vierge (logo, nom, responsable, coordonnées, filet orange, pied avec IFU / adresse / position GPS), affiché dans le lecteur interne.
- Écran : `composants/FicheCentre.jsx` (logo avec aperçu, géolocalisation « Utiliser ma position » + lien carte OpenStreetMap), `pages/FicheCentre.jsx`. Tests : `backend/tests/test_multi_centres.py`.

## Vue du groupe, transfert de patient, centre en haut (lot 18, propriétaire, 19/11/2026)
- **Centre tout en haut** : barre fixe en haut de CHAQUE écran (`composants/MiseEnPage.jsx`, `data-testid="barre-centre"`) : logo et nom du centre (imposé) ou liste déroulante (comptes du groupe) ; la page se recharge au changement de centre.
- **Synthèse des centres** (`backend/app/groupe.py`, `GET /groupe/synthese`, écran « Synthèse Des Centres ») : réservée au directeur général et au super administrateur SANS centre (`groupe`) ; une ligne par centre + totaux collés sous le tableau (règle 25), taux recalculés sur les totaux ; AGRÉGÉE, aucune identité de patient.
  Seules routes à franchir les centres : le centre courant est fixé le temps du calcul de chaque ligne puis rétabli (`db.fixer_centre`).
- **Transfert d'un patient** (`POST /patients/{id}/transfert`, super administrateur seul, centre de départ choisi) : CONSENTEMENT du patient obligatoire + motif (liste finie) ; le dossier est COPIÉ dans le centre d'arrivée (nouveau code du centre, bilans copiés, poste / modèle d'adhésion / organisme retirés) ;
  au départ le patient passe « Transféré » (`transfere_vers`) et ses séances planifiées sont annulées, l'historique de séances et de factures y reste ; journalisé dans les DEUX centres (`patient_transfere_depart` / `patient_transfere_arrivee`). Tests : `backend/tests/test_groupe.py`.

## Pastilles de notifications dans le menu (RÈGLE PERMANENTE du propriétaire, 19/11/2026 : « pour toutes les plateformes disposant d'une sidebar »)
- Chaque lien de menu qui reçoit des notifications affiche une BULLE avec le NOMBRE d'éléments non encore traités / lus : Centre de Messagerie, Réservations, Alertes, Stock… Le nombre est écrit (jamais la couleur seule), plafonné à « 99+ », avec une étiquette d'accessibilité.
- Mise en œuvre ici : `GET /notifications/compteurs` (`backend/app/notifications.py`, une seule route légère pour tout le menu, filtrée par centre ET par rôle, calculs lourds gardés 60 s) ; `lib/contexte.jsx` relit les compteurs toutes les 30 s et après chaque action qui les change (`rafraichirCompteurs`) ;
  `composants/MiseEnPage.jsx` dessine la pastille (`data-testid="pastille-<lien>"`). Tout NOUVEAU lien qui reçoit des notifications ajoute sa clé dans `notifications.py` (test `test_pastilles_de_notifications`).

## Messagerie WhatsApp, activité et notifications automatiques (lot 19, propriétaire, 19/11/2026 : « comme avec ALBARKA… comme sur SAWALI »)
- **Centre de messagerie WA** (`backend/app/messagerie.py`, écran « Centre De Messagerie WA ») : contacts (import des patients), conversations, modèles, envoi de DOCUMENTS (facture DU patient du contact, papier à en-tête A4 / A5, fichier PDF / JPEG / PNG de 5 Mo au plus ; protocole v3 de Liluvine : champ `media` en base64, 10 Mo au plus),
  rappels de séances groupés, demandes de réservation reçues. Rôles : secrétariat et administration. Départ en ARRIÈRE-PLAN (règle 7) : statut « en cours » → « envoyé » → « remis » → « lu » / « échec » ; un numéro désinscrit (STOP) ne reçoit rien (409) ; le texte des messages n'est jamais journalisé.
  Collections par centre : `contacts` (numéro unique dans un centre), `wa_messages`, `wa_modeles`, `wa_demandes`. Aucune donnée médicale ne part par WhatsApp.
- **Adresse de retour de SAWALI** (règle 7) : `POST /api/webhooks/liluvine-retour`, signée HMAC (`X-Timestamp`, `X-Signature`, 5 minutes) avec `LILUVINE_WA_HMAC` ; types `statut` (remis / lu / échec), `reponse` (rangée dans le centre auquel on a écrit le plus récemment ; « 1 » / « 2 » confirment ou excusent la prochaine séance ; un mot comme RDV crée une demande + accusé automatique), `desinscription`, `stats_du_jour`
  (indicateurs agrégés de tous les centres, sans donnée de patient). À saisir dans SAWALI (émetteur « dialyse » → URL de retour) : `https://api.looisdialyse.cloud/api/webhooks/liluvine-retour`.
- **Activité** (`backend/app/activite.py`) : RÉSERVATIONS (demandée → confirmée : le serveur crée alors la séance planifiée avec tous les contrôles du planning ; refusée ; annulée : annule aussi la séance encore planifiée), CALENDRIER interactif (`GET /calendrier` : un mois, séances par état, réservations en attente, occupation, maintenances de postes ;
  `GET /calendrier/jour` : grille postes × créneaux, sans détail médical pour le secrétariat), LISTE D'ATTENTE (priorité urgente / normale / basse). Écrans « Calendrier D'Activité » (clic sur un jour = grille, réservation d'une place libre) et « Réservations » (réservations, demandes WhatsApp à convertir, liste d'attente).
- **Notifications automatiques du patient** (`messagerie.notifier`, option PAR CENTRE, éteinte par défaut, réglée par l'administration dans l'onglet « Notifications auto ») : rendez-vous pris (réservation confirmée), réservation refusée / annulée, séance annulée, séance terminée, RAPPEL « X heures avant » (X réglable de 1 à 72 h, un seul rappel par séance,
  tâche de fond toutes les 5 minutes `rappels_automatiques`), contrôle à renouveler (bilan de plus de 35 jours, un rappel tous les 14 jours, désactivé par défaut). Textes = modèles modifiables ; rien si l'événement est coupé, si WhatsApp n'est pas configuré, si le patient n'a pas de numéro valide ou s'est désinscrit. Tests : `test_messagerie.py`, `test_activite.py`, `test_notifications_wa.py`.

## Tableau de bord « Aujourd'hui » (lot 20, propriétaire, 19/11/2026 : « fais le tableau de bord Aujourd'hui en priorité »)
- `backend/app/aujourdhui.py`, `GET /aujourdhui` (secrétariat, soignants, administration) : photographie de la journée EN COURS pour le centre de travail (heure UTC = heure du Burkina Faso), calculée par `calculer(maintenant, role)` (fonction testable à une heure donnée) ; lectures en bloc (règle 7).
  Par poste : état (libre, en dialyse, maintenance, hors service), séance en cours (patient, début, fin prévue, temps restant, progression, durée dépassée), prochaine séance, nombre de séances terminées. En haut : séances en RETARD à démarrer (15 minutes après l'heure prévue), durées dépassées, fins dans moins de 30 minutes,
  patients empêchés (réponse WhatsApp « 2 »), chiffres du jour, réservations / demandes WhatsApp à traiter, séances à valider (médecin). Les alertes cliniques ne sont envoyées qu'au personnel médical (`sea._public`) ; le secrétariat voit l'organisation sans détail médical.
- Durée d'une séance : durée prévue saisie au démarrage, sinon prescription du patient, sinon 240 min. Écran « Aujourd'hui » (`pages/Aujourdhui.jsx`) : relu toutes les 30 s, bouton « Actualiser » avec toast ; page d'accueil du secrétariat ; PASTILLE du menu = nombre de séances en retard (`notifications.py`, clé `/aujourdhui`). Tests : `backend/tests/test_aujourdhui.py` (heures FIXÉES : jamais dépendants de l'heure réelle ni de minuit).

## Gestion du centre : personnel, maintenance, eau, rentabilité (lot 21, propriétaire, 19/11/2026)
- **Planning du personnel** (`backend/app/personnel.py`, écran « Planning Du Personnel ») : équipe (`personnel`) et affectations (`affectations`) par jour et par créneau, absences (congé, maladie, formation ; « journée » = les 3 créneaux), conflits refusés (409), copie d'une semaine vers la suivante.
  COUVERTURE calculée par le serveur : séances prévues / `patients_par_infirmier` (4 par défaut, réglable) = soignants requis, et un néphrologue à chaque créneau qui a des séances ; un manque = alerte (créneau rouge, pastille « Planning du personnel »), jamais un blocage. Le coût mensuel d'un salarié n'est vu que de l'administration et de la direction.
- **Maintenance des postes** (`backend/app/maintenance.py`) : interventions (préventive, corrective, désinfection, sécurité électrique, étalonnage…) planifiée → en cours (le poste passe « en maintenance » ; refusé si une séance est en cours dessus) → terminée (coût, durée, carnet du poste, poste « en service », prochaine maintenance recalculée) ou annulée ;
  la date prévue alimente le calendrier d'activité ; compteur de séances depuis la dernière préventive (seuils 500 séances / 180 jours dans le code, à valider avec le technicien biomédical) ; pastille = interventions à démarrer. Écriture : technicien et administration.
- **Contrôle de l'eau** (`backend/app/eau.py`) : relevés quotidiens (chlore total, dureté résiduelle, conductivité) et mensuels (bactériologie, endotoxines) avec limites et seuils d'alerte USUELS regroupés dans `TESTS` (À VALIDER par le médecin responsable et le technicien) ; niveau calculé par `niveau()` (fonction pure) ; un relevé hors seuil exige une ACTION CORRECTIVE documentée (`/eau/controles/{id}/traiter`) ;
  pastille = contrôles manquants + relevés non traités ; courbe des 30 derniers jours.
- **Rentabilité** (`backend/app/rentabilite.py`, administration et direction) : par mois entier (`de` / `a` au format AAAA-MM, 24 mois au plus, 6 par défaut) : facturé et encaissé (factures non annulées), coûts = personnel + maintenance terminée + charges saisies (`charges` : consommables et médicaments = VARIABLE, le reste fixe), marge, taux de marge, coût et recette par séance, SEUIL de rentabilité = coûts fixes / (recette moyenne − coût variable moyen) ;
  totaux collés sous le tableau (règle 25), pourcentages jamais additionnés. Nouvelles collections par centre : `personnel`, `affectations`, `interventions`, `controles_eau`, `charges`. Tests : `backend/tests/test_gestion_centre.py`.

## Piège React à éviter : fonctions passées en propriété (lot 23, constat du 20/11/2026 sur la vidéo du propriétaire : « je ne peux rien saisir »)
- Une fonction passée en propriété à un composant enfant (`onChange={() => …}`) change à CHAQUE rendu du parent. Si l'enfant la met dans les dépendances d'un `useCallback` ou d'un `useEffect` qui charge des données ET remet des champs à zéro, l'effet se relance en boucle : jauge sans fin, saisie effacée.
  Règle : garder une telle fonction dans une RÉFÉRENCE (`const ref = useRef(f); ref.current = f;`) ; ne remettre un champ à zéro que dans un effet qui dépend de l'IDENTIFIANT de l'objet affiché (ex. `[contact.id]`), jamais de la fonction de chargement. Modèle : `Conversation` dans `pages/Messagerie.jsx`.
- Libellés de menu : un sigle s'écrit déjà en majuscules dans le libellé (« centre de messagerie WA ») : `titreMenu` ne met en majuscule que la première lettre de chaque mot et ne baisse jamais le reste.

## Ligne WhatsApp par centre (lot 24, propriétaire, 20/11/2026 : « prépare le second canal, une ligne par centre »)
- Deux canaux : ligne PARTAGÉE (émetteur « dialyse », `LILUVINE_WA_HMAC`) et ligne PROPRE à un centre (fiche du centre : `wa_emetteur`, réservé au super administrateur ; clé dans la variable Render `LILUVINE_WA_HMAC_<PRÉFIXE>`, jamais dans le dépôt ni dans le chat).
- Envoi : `whatsapp.envoyer(..., centre_id)` utilise la ligne du centre si l'émetteur ET sa clé existent, sinon la ligne partagée ; `wa_repli` (facultatif) autorise la ligne partagée en cas de panne (jamais pour un désinscrit « 409 » ni des données invalides).
- Retour : `/api/webhooks/liluvine-retour` essaie toutes les clés ; la clé qui valide la signature DÉSIGNE le centre (réponses, STOP, statistiques restent dans ce centre ; numéro inconnu = « Nouveau contact » de ce centre). `GET /messagerie/etat` indique le canal (`ligne_centre` / `partagee` / `aucun`). Tests : `backend/tests/test_ligne_par_centre.py`.

## Fond de la page d'accueil (lot 25, propriétaire, 20/11/2026 : « permet à l'admin de définir une image ou une vidéo de fond pour la page d'accueil »)
- Menu « Apparence De L'Accueil » (super administrateur seul, `pages/FondAccueil.jsx`) : choix d'une image (PNG / JPEG / WebP, 8 Mo au plus, réduite à 1920 px et ré-encodée en JPEG) ou d'une vidéo (MP4 / WebM, 12 Mo au plus, conservée telle quelle, lue sans son et en boucle), aperçu, assombrissement réglable (0 à 80 %, bouton Enregistrer actif si modifié), retrait. Un seul fond pour tous les centres.
- Serveur `backend/app/fond_accueil.py` : le TYPE est lu dans le CONTENU (jamais l'extension ; SVG, GIF et exécutables refusés), lecture PUBLIQUE (`GET /fond-accueil`, `GET /fond-accueil/media` avec Range, `nosniff`, cache long, adresse `?v=<version>`), envoi par `PUT /fond-accueil/media` (corps = octets bruts), `PUT /fond-accueil/reglages`, `DELETE /fond-accueil`. Collection `fond_accueil` (une ligne), HORS sauvegardes chiffrées ; changements journalisés (jamais le contenu).
- Écran : `composants/FondAccueil.jsx` affiche le fond derrière la carte de connexion ; la vidéo n'est pas lue si la personne a demandé moins d'animations. Tests : `backend/tests/test_fond_accueil.py`.

## Administrateur multi-centres (lot 26, propriétaire, 20/11/2026 : « passe à l'étape suivante »)
- Un compte « administrateur » rattaché à un centre peut recevoir des centres SUPPLÉMENTAIRES (`centres_ids` sur le compte) : attribution par le SUPER ADMINISTRATEUR seul (Gestion Des Comptes → case « Centres supplémentaires » ; le serveur refuse tout autre appelant et tout rôle autre qu'administrateur), centres existants, 20 au plus, sans doublon ; un compte qui cesse d'être administrateur les perd.
- `auth._lire_utilisateur` : l'en-tête `X-Centre` n'est honoré QUE pour ces comptes et QUE pour un centre de leur liste (sinon 403) ; sans choix, centre principal. Le compte reçoit `multi_centres`, `centres_ids` (principal + supplémentaires) et `centre_principal`. Pour tout autre compte rattaché, `X-Centre` reste ignoré (aucun passage d'un centre à l'autre). Ce n'est PAS un compte du groupe : pas de synthèse des centres, pas de transfert de patient, pas de création de centre.
- Écran : sélecteur de centre en haut de l'écran (ses centres seulement, sans « — Choisir — »), pastille « +n centres » dans la liste des comptes. `GET /centres` ne rend que ses centres. Comptes créés ou gérés = ceux du centre de travail choisi. Tests : `backend/tests/test_admin_multicentres.py`.

## Consommables valorisés dans la rentabilité (lot 27, propriétaire, 20/11/2026 : « passe à l'étape suivante »)
- Prix unitaire d'achat PAR LOT (`cout_unitaire`, FCFA entier, facultatif) saisi à la réception (« Entrée de stock ») ; un lot existant garde son prix (autre prix = 409). `stock._mouvement` calcule pour chaque sortie ou perte `valeur` (quantité × prix du lot, relu sur le lot) et `sans_prix` (quantité sortie d'un lot sans prix).
- Rentabilité : `consommables_stock` (colonne « Conso. stock ») = valeur des sorties et pertes du mois, ajoutée aux COÛTS VARIABLES ; `conso_sans_prix` n'est jamais devinée : l'écran l'affiche en alerte. Ne plus saisir à la main, pour un mois suivi par le stock, la charge « Consommables et médicaments » (double comptage). Les mouvements d'avant le lot 27 n'ont pas de valeur.
- Confidentialité : prix, `valeur` et `sans_prix` ne sont vus que de l'ADMINISTRATION (`stock._masquer_prix`, appliqué par le serveur à `/stock/mouvements`, `/stock/articles/{id}/lots` et aux réponses d'entrée / sortie) ; jamais dans la liste des lots utilisés d'une séance. Tests : `backend/tests/test_gestion_centre.py` (consommables valorisés).

## Prévisions de stock et bon de commande (lot 28, propriétaire, 20/11/2026 : « passe à l'étape suivante »)
- `backend/app/stock_prevision.py`, écran « Prévisions Et Commande » (`pages/PrevisionsStock.jsx`, bouton « Prévisions et commande » sur Consommables Et Stocks) : pour chaque article actif, consommation des 30 derniers jours (sorties et pertes), BESOIN de la période (15, 30, 60 ou 90 jours : séances PLANIFIÉES x quantité par séance pour les articles « par séance », sinon consommation x durée), stock UTILISABLE (lots non périmés ; les périmés sont signalés à part), jours restants et date de rupture estimée,
  QUANTITÉ À COMMANDER = besoin + seuil d'alerte (stock de sécurité) − stock utilisable, arrondie à l'unité supérieure. États : Rupture (rien d'utilisable), Urgent (moins de 7 jours), À commander, Suffisant. Lectures en bloc (règle 7), cloisonné par centre. Une prévision AIDE à commander, elle ne commande rien toute seule.
- Prix : dernier lot reçu AVEC prix (lot 27) ; coût estimé et prix visibles de l'ADMINISTRATION seule (le serveur les retire pour les autres rôles) ; un article à commander sans prix est signalé (jamais deviné). Lecture : médecin, infirmier, technicien, administration ; bon de commande : infirmier, technicien, administration.
- `GET /stock/bon-commande` : PDF A4 sur le papier à en-tête du centre (logo, coordonnées), une ligne par article en rupture / urgent / à commander, nombres à droite, total du coût pour l'administration, lignes « Établi par » et « Validé par » ; affiché dans le lecteur interne ; journalisé (`bon_commande_genere`). Tests : `backend/tests/test_previsions_stock.py` (dates FIXÉES).

## Journal de diagnostic des retours WhatsApp (lot 29, propriétaire, 20/11/2026 : « finalise tout ce qui restait pour Dialyse »)
- `POST /api/webhooks/liluvine-retour` écrit dans le journal du serveur (Render, logger « uvicorn.error ») : pour un `statut`, l'état de remise (sent / delivered / read / failed), l'identifiant du message, la cause éventuelle et la ligne (`partagee` ou `centre`) ; pour les autres types, le type seul. JAMAIS le texte d'un message ni un numéro. Même principe que ShuyahStore (lot 40). Test : `test_journal_de_diagnostic_des_retours_sans_texte_ni_numero`.
- État constaté le 20/11/2026 : Dialyse 1.25 en ligne (looisdialyse.cloud / api.looisdialyse.cloud), WhatsApp configuré (le retour signé de SAWALI est accepté, plusieurs appels 200 le jour même), `FRONTEND_ORIGIN` en `sync: false` dans `render.yaml` (une fusion ne l'écrase donc pas : leçon de ShuyahStore).
- RAPPEL à donner à chaque livraison touchant WhatsApp : SAWALI → émetteur « dialyse » → URL de retour = `https://api.looisdialyse.cloud/api/webhooks/liluvine-retour` ; pour la ligne d'un centre : émetteur dédié → même URL de retour, clé dans la variable Render `LILUVINE_WA_HMAC_<PRÉFIXE>`.
