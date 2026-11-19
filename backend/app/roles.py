"""
Rôles et permissions de la clinique de dialyse.

Principe de confidentialité : les données MÉDICALES (sérologies, antécédents, allergies, prescription, accès vasculaires,
constantes des séances) ne sont visibles que du personnel soignant et de l'administration ; le secrétariat ne voit que
l'identité et l'organisation (planning). Liste finie de rôles = liste déroulante dans l'interface (règle 10).
"""

SUPER_ADMIN = "super_admin"       # propriétaire de la plateforme : tout, y compris suppression et récupération
ADMIN = "admin"                   # administrateur de la clinique : comptes, postes, paramètres, journal
MEDECIN = "medecin"               # néphrologue : prescription, validation des séances
INFIRMIER = "infirmier"           # soins : planning, déroulement des séances
DIRECTION = "direction"           # directeur général : rapports et indicateurs AGRÉGÉS, jamais l'identité des patients
SECRETARIAT = "secretariat"       # accueil : identité des patients, planning (pas de données médicales)
TECHNICIEN = "technicien"         # biomédical : postes et machines uniquement

TOUS_LES_ROLES = [SUPER_ADMIN, ADMIN, DIRECTION, MEDECIN, INFIRMIER, SECRETARIAT, TECHNICIEN]
LIBELLES = {SUPER_ADMIN: "Super administrateur", ADMIN: "Administrateur", DIRECTION: "Directeur général", MEDECIN: "Médecin néphrologue",
            INFIRMIER: "Infirmier(ère)", SECRETARIAT: "Secrétariat", TECHNICIEN: "Technicien biomédical"}

# Rôles qu'un ADMIN peut créer ou modifier (jamais un autre admin ni un super admin).
ROLES_GERES_PAR_ADMIN = {DIRECTION, MEDECIN, INFIRMIER, SECRETARIAT, TECHNICIEN}

ADMINISTRATION = {ADMIN, SUPER_ADMIN}
# Rôles pouvant ne dépendre d'AUCUN centre précis (compte « du groupe ») : ils choisissent alors le centre où ils travaillent (en-tête X-Centre).
# Tous les autres rôles sont rattachés à UN centre, qu'ils ne peuvent pas quitter.
ROLES_GROUPE = {SUPER_ADMIN, DIRECTION}
SOIGNANTS = {MEDECIN, INFIRMIER}
# Données médicales : soignants + administration.
VOIT_MEDICAL = {MEDECIN, INFIRMIER, ADMIN, SUPER_ADMIN}
# Identité des patients : tous sauf le technicien.
LECTURE_PATIENT = {MEDECIN, INFIRMIER, SECRETARIAT, ADMIN, SUPER_ADMIN}
# Création / modification de l'identité (accueil) et du dossier médical.
ECRITURE_IDENTITE = {SECRETARIAT, MEDECIN, INFIRMIER, ADMIN, SUPER_ADMIN}
ECRITURE_MEDICAL = {MEDECIN, INFIRMIER, ADMIN, SUPER_ADMIN}
# Prescription de dialyse et validation des séances : médecin seulement (+ administration pour dépannage).
PRESCRIPTION = {MEDECIN, ADMIN, SUPER_ADMIN}
VALIDATION_SEANCE = {MEDECIN, ADMIN, SUPER_ADMIN}
# Planning (créer / déplacer / annuler une séance) : accueil et soignants.
PLANNING = {SECRETARIAT, MEDECIN, INFIRMIER, ADMIN, SUPER_ADMIN}
# Déroulement d'une séance (constantes, incidents, début, fin) : soignants.
DEROULEMENT = {MEDECIN, INFIRMIER, ADMIN, SUPER_ADMIN}
# Lecture des séances : même périmètre que le planning (le secrétariat ne voit pas le détail médical, voir seances.py).
LECTURE_SEANCE = {SECRETARIAT, MEDECIN, INFIRMIER, ADMIN, SUPER_ADMIN}
# Postes (machines) : écriture par la technique et l'administration.
ECRITURE_POSTE = {TECHNICIEN, ADMIN, SUPER_ADMIN}
LECTURE_POSTE = set(TOUS_LES_ROLES)
# Statistiques : encadrement et soignants.
LECTURE_STATS = {MEDECIN, INFIRMIER, ADMIN, SUPER_ADMIN}
# Rapports et tableau de bord AGRÉGÉS (aucun nom de patient) : les statistiques + la direction.
LECTURE_RAPPORTS = LECTURE_STATS | {DIRECTION}
LECTURE_JOURNAL = ADMINISTRATION
# Consommables et stocks : lecture par les équipes de soins et la technique ; écriture (entrées, sorties, ajustements) par les infirmiers, la technique et l'administration.
LECTURE_STOCK = {MEDECIN, INFIRMIER, TECHNICIEN, ADMIN, SUPER_ADMIN}
ECRITURE_STOCK = {INFIRMIER, TECHNICIEN, ADMIN, SUPER_ADMIN}
# Facturation : caisse et secrétariat ; paramétrage (tarifs, organismes, annulation) : administration. Aucune donnée médicale n'y figure.
FACTURATION = {SECRETARIAT, ADMIN, SUPER_ADMIN}
# Suppression d'un patient (sans séance) : administration seulement.
SUPPRESSION = ADMINISTRATION


def voit_medical(role: str) -> bool:
    """Vrai si ce rôle peut voir les données médicales."""
    return role in VOIT_MEDICAL
