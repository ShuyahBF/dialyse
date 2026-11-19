# Dialyse — gestion des actes de dialyse d'une clinique

Application web (serveur FastAPI + MongoDB, site React) calquée sur l'architecture de « Déplacés internes » :
comptes à rôles, journal d'audit, double authentification, données sensibles masquées selon le rôle.

## Ce que fait la version 1.1 (lot 1)
- **Patients** : identité, dossier médical (sérologies, allergies, antécédents, poids sec), **prescription de dialyse**
  (durée, jours, créneau, dialyseur, débits, bain, anticoagulation), **accès vasculaires** (fistule, cathéter…), statut.
- **Postes** (machines) : état, **isolement sérologique** (VHB / VHC / VIH), carnet de maintenance.
- **Planning** : grille postes × créneaux ; **génération automatique** de la semaine d'après les prescriptions ;
  refus des conflits (poste ou patient déjà occupé) ; alerte si un patient à sérologie positive est placé hors poste d'isolement.
- **Séance (acte de dialyse)** : démarrage (poids, tension), surveillance, incidents, clôture (UF, Kt/V, durée),
  **validation et verrouillage par le médecin**. Alertes cliniques calculées (hypotension, prise de poids, Kt/V insuffisant, UF rapide…).
- **Tableau de bord**, **journal d'audit** (chaque ouverture d'un dossier est tracée), **gestion des comptes**, double authentification.

## Nom de domaine
Site : `https://looisdialyse.cloud` · API : `https://api.looisdialyse.cloud` (déclarés dans `render.yaml`, `domains`). Les anciennes adresses onrender.com ne sont plus utilisées. `FRONTEND_ORIGIN` = `https://looisdialyse.cloud`.

## Multi-centres
Plusieurs centres de dialyse sur la même plateforme, sur le modèle d'e-Kol : chaque centre a ses patients, postes, séances, bilans, stocks, factures et comptes. Le super administrateur crée les centres
(« Centres De Dialyse ») puis l'administrateur de chaque centre (« Gestion Des Comptes »). Les comptes d'un centre ne voient jamais un autre centre ; le super administrateur et le directeur général choisissent le centre dans la barre latérale.
Les données existantes sont rattachées automatiquement à « Centre principal » (préfixe DIAL).

## Rôles
| Rôle | Droits |
|---|---|
| Super administrateur / Administrateur | tout, comptes, journal, suppression (patient sans séance) |
| Médecin néphrologue | dossier, **prescription**, **validation des séances** |
| Infirmier(ère) | dossier médical, déroulement des séances |
| Secrétariat | identité et planning ; **jamais** les données médicales (le serveur ne les envoie pas) |
| Technicien biomédical | postes et maintenance uniquement |

## Lancer en local
```bash
cd backend && pip install -r requirements-test.txt && python -m pytest tests -q     # 28 tests
cd frontend && npm install && npm test && npm run build
```
Variables du serveur : voir `backend/app/config.py` (jamais de secret dans le dépôt).

## Déploiement
`render.yaml` crée deux services sur Render : `dialyse-api` (serveur) et `dialyse-web` (site statique).
Saisir dans Render : `MONGODB_URI`, `SUPERADMIN_LOGIN`, `SUPERADMIN_MOT_DE_PASSE`, `FRONTEND_ORIGIN` (adresse du site) et, côté site, `VITE_API_URL` (adresse du serveur).
Au premier démarrage le super administrateur est créé (mot de passe à changer à la première connexion).

## À venir (lots suivants, à valider avec la clinique)
Bilans biologiques et courbes, consommables et stock, facturation / prise en charge, rapport journalier, sauvegardes chiffrées,
connexion par WhatsApp. Les seuils d'alerte cliniques (`backend/app/alertes.py`) sont des valeurs usuelles **à valider par le médecin responsable**.
