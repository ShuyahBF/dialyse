"""
Patients : identité, dossier médical, prescription de dialyse, accès vasculaires.

Confidentialité : le secrétariat ne reçoit JAMAIS les champs médicaux (voir CHAMPS_MEDICAUX) ; chaque ouverture d'un dossier est journalisée.
Un patient n'est jamais supprimé s'il a des séances (on change son statut) ; la suppression est réservée à l'administration.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from . import adhesion, db, historique, roles, validation
from .auth import exiger_roles, journaliser, utilisateur_courant

routeur = APIRouter()

SEXES = ["M", "F"]
GROUPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
STATUTS = ["actif", "hospitalise", "transfere", "greffe", "arret", "decede"]
LIBELLE_STATUT = {"actif": "En dialyse", "hospitalise": "Hospitalisé", "transfere": "Transféré", "greffe": "Greffé",
                  "arret": "Dialyse arrêtée", "decede": "Décédé"}
CAUSES = ["Néphropathie diabétique", "Néphroangiosclérose hypertensive", "Glomérulonéphrite chronique", "Polykystose rénale",
          "Uropathie obstructive", "Néphropathie interstitielle", "Insuffisance rénale aiguë non récupérée", "Indéterminée"]
SEROLOGIES = ["negatif", "positif", "inconnu"]
PRISES_EN_CHARGE = ["Aucune (paiement direct)", "Assurance maladie", "Mutuelle / assurance privée", "Employeur", "Prise en charge sociale"]
TYPES_ACCES = ["Fistule artério-veineuse (FAV)", "Pontage prothétique", "Cathéter tunnellisé", "Cathéter temporaire"]
ANTICOAGULATIONS = ["Héparine standard", "HBPM", "Sans héparine", "Citrate"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
CRENEAUX = ["matin", "midi", "soir"]

# Champs visibles du seul personnel médical et de l'administration.
CHAMPS_MEDICAUX = {"groupe_sanguin", "cause_irc", "date_debut_dialyse", "serologies", "allergies", "antecedents", "poids_sec",
                   "prescription", "acces_vasculaires"}
CHAMPS_IDENTITE = {"nom", "prenom", "sexe", "date_naissance", "telephone", "adresse", "personne_a_prevenir", "prise_en_charge", "numero_assurance", "organisme_id", "taux_prise_en_charge"}


def masquer(doc: dict, role: str, modeles: dict | None = None) -> dict:
    """Copie du patient sans _id ; sans champs médicaux pour un rôle qui n'y a pas droit."""
    d = {k: v for k, v in doc.items() if k not in ("_id", "nom_norm", "prenom_norm")}
    d["age"] = validation.age(d.get("date_naissance", ""))
    d["statut_libelle"] = LIBELLE_STATUT.get(d.get("statut", ""), d.get("statut", ""))
    # Dossier d'adhésion : modèle du patient (celui choisi, sinon le modèle par défaut) ; `modeles` est lu une seule fois pour toute une liste
    modele = adhesion.modele_de(doc, modeles if modeles is not None else adhesion.dictionnaire())
    d["dossier_adhesion"] = adhesion.etat_dossier(d.get("pieces_admission"), modele["pieces"])
    d["modele_adhesion"] = {"id": modele["id"], "nom": modele["nom"], "centre": modele.get("centre", ""), "pieces": modele["pieces"]}
    if not roles.voit_medical(role):
        for k in CHAMPS_MEDICAUX:
            d.pop(k, None)
    return d


def prochain_code() -> str:
    """
    Code patient séquentiel du CENTRE : « <préfixe du centre>-000001 » (ex. DIAL-000001, CMC-000001). Le compteur est atomique et propre à chaque
    centre (la collection `parametres` est filtrée par centre).
    """
    from pymongo import ReturnDocument
    centre = db.brut().centres.find_one({"id": db.centre_courant.get()}) or {}
    c = db.base().parametres.find_one_and_update({"id": "compteur_patients"}, {"$inc": {"n": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    return f"{centre.get('prefixe') or 'DIAL'}-{int(c['n']):06d}"


def _identite(corps: dict, creation: bool) -> dict:
    """Champs d'identité validés (seulement ceux présents, sauf en création)."""
    d: dict = {}
    if creation or "nom" in corps:
        d["nom"] = validation.texte(corps, "nom", "Nom", True, 80).upper()
    if creation or "prenom" in corps:
        d["prenom"] = validation.texte(corps, "prenom", "Prénom", True, 80)
    if creation or "sexe" in corps:
        d["sexe"] = validation.choix(corps, "sexe", "Sexe", SEXES, obligatoire=True)
    if creation or "date_naissance" in corps:
        d["date_naissance"] = validation.date_iso(corps, "date_naissance", "Date de naissance", True, futur_ok=False)
    for cle, lib in (("telephone", "Téléphone"), ("adresse", "Adresse"), ("numero_assurance", "Numéro d'assurance")):
        if cle in corps:
            d[cle] = validation.texte(corps, cle, lib, False, 120)
    if "prise_en_charge" in corps:
        v = validation.texte(corps, "prise_en_charge", "Prise en charge", False, 80)
        d["prise_en_charge"] = v                       # liste déroulante + « Autre… » : une valeur libre reste admise (règle 10)
    if "organisme_id" in corps:
        oid = str(corps.get("organisme_id") or "")
        if oid and not db.base().organismes.find_one({"id": oid}):
            validation.erreur("Organisme payeur inconnu")
        d["organisme_id"] = oid
    if "taux_prise_en_charge" in corps:
        d["taux_prise_en_charge"] = validation.nombre(corps, "taux_prise_en_charge", "Taux de prise en charge (%)", 0, 100)
    if "personne_a_prevenir" in corps:
        p = corps.get("personne_a_prevenir") or {}
        d["personne_a_prevenir"] = {"nom": validation.texte(p, "nom", "Personne à prévenir", False, 80),
                                    "telephone": validation.texte(p, "telephone", "Téléphone de la personne à prévenir", False, 40),
                                    "lien": validation.texte(p, "lien", "Lien", False, 40)}
    return d


def _medical(corps: dict) -> dict:
    """Champs médicaux validés (seulement ceux présents)."""
    d: dict = {}
    if "groupe_sanguin" in corps:
        d["groupe_sanguin"] = validation.choix(corps, "groupe_sanguin", "Groupe sanguin", GROUPES)
    if "cause_irc" in corps:
        d["cause_irc"] = validation.texte(corps, "cause_irc", "Cause de l'insuffisance rénale", False, 120)
    if "date_debut_dialyse" in corps:
        d["date_debut_dialyse"] = validation.date_iso(corps, "date_debut_dialyse", "Début de la dialyse")
    if "serologies" in corps:
        s = corps.get("serologies") or {}
        d["serologies"] = {k: validation.choix(s, k, "Sérologie " + k.upper(), SEROLOGIES, defaut="inconnu") or "inconnu" for k in ("vhb", "vhc", "vih")}
    for cle, lib in (("allergies", "Allergies"), ("antecedents", "Antécédents")):
        if cle in corps:
            d[cle] = validation.texte(corps, cle, lib, False, 1000)
    if "poids_sec" in corps:
        d["poids_sec"] = validation.nombre(corps, "poids_sec", "Poids sec (kg)", 20, 250)
    if "statut" in corps:
        d["statut"] = validation.choix(corps, "statut", "Statut", STATUTS, obligatoire=True)
    return d


def valider_prescription(p: dict) -> dict:
    """Prescription de dialyse (médecin) : durée, fréquence, jours, créneau, dialyseur, débits, bain, anticoagulation."""
    jours = [j for j in (p.get("jours") or []) if j in JOURS]
    if len(jours) != len(p.get("jours") or []):
        validation.erreur("Jours : valeur non reconnue")
    freq = validation.nombre(p, "frequence_semaine", "Séances par semaine", 1, 7)
    if jours and freq and len(jours) != int(freq):
        validation.erreur("Le nombre de jours choisis doit égaler le nombre de séances par semaine")
    bain = p.get("bain") or {}
    return {"duree_min": validation.nombre(p, "duree_min", "Durée (min)", 60, 480), "frequence_semaine": freq, "jours": jours,
            "creneau": validation.choix(p, "creneau", "Créneau habituel", CRENEAUX),
            "dialyseur": validation.texte(p, "dialyseur", "Dialyseur", False, 80),
            "debit_sang": validation.nombre(p, "debit_sang", "Débit sang (ml/min)", 100, 600),
            "debit_dialysat": validation.nombre(p, "debit_dialysat", "Débit dialysat (ml/min)", 300, 800),
            "anticoagulation": validation.texte(p, "anticoagulation", "Anticoagulation", False, 60),
            "heparine_ui": validation.nombre(p, "heparine_ui", "Héparine (UI)", 0, 20000),
            "bain": {"potassium": validation.nombre(bain, "potassium", "Potassium du bain", 0, 5),
                     "calcium": validation.nombre(bain, "calcium", "Calcium du bain", 0, 2.5),
                     "sodium": validation.nombre(bain, "sodium", "Sodium du bain", 130, 150),
                     "bicarbonate": validation.nombre(bain, "bicarbonate", "Bicarbonate du bain", 20, 40)},
            "notes": validation.texte(p, "notes", "Notes de prescription", False, 500)}


@routeur.get("/listes")
def listes(u: dict = Depends(utilisateur_courant)):
    """Listes finies de l'application (listes déroulantes de l'interface)."""
    return {"sexes": SEXES, "groupes": GROUPES, "statuts": [{"valeur": s, "libelle": LIBELLE_STATUT[s]} for s in STATUTS], "causes": CAUSES,
            "serologies": SEROLOGIES, "prises_en_charge": PRISES_EN_CHARGE, "types_acces": TYPES_ACCES, "anticoagulations": ANTICOAGULATIONS,
            "jours": JOURS, "creneaux": CRENEAUX, "etats_piece": adhesion.ETATS_PIECE}


@routeur.get("/patients")
def lister(q: str = "", statut: str = "", dossier: str = "", u: dict = Depends(exiger_roles(roles.LECTURE_PATIENT))):
    """Liste des patients (recherche sur nom, prénom, code, téléphone ; filtre par statut). Résumé seulement ; le dossier complet s'ouvre un par un."""
    filtre: dict = {}
    if statut:
        filtre["statut"] = statut
    if q.strip():
        n = validation.normaliser(q)
        filtre["$or"] = [{"nom_norm": {"$regex": n}}, {"prenom_norm": {"$regex": n}}, {"code": {"$regex": q.strip().upper()}},
                         {"telephone": {"$regex": q.strip()}}]
    lignes = []
    modeles = adhesion.dictionnaire()
    for p in db.base().patients.find(filtre).sort([("nom_norm", 1), ("prenom_norm", 1)]).limit(2000):
        m = masquer(p, u["role"], modeles)
        if dossier == "incomplet" and m["dossier_adhesion"]["complet"]:
            continue
        serologie_positive = roles.voit_medical(u["role"]) and any(v == "positif" for v in (p.get("serologies") or {}).values())
        lignes.append({k: m.get(k) for k in ("id", "code", "nom", "prenom", "sexe", "age", "telephone", "statut", "statut_libelle", "prise_en_charge", "dossier_adhesion")} | {"modele_adhesion": m["modele_adhesion"]["nom"]}
                      | ({"serologie_positive": serologie_positive, "poids_sec": m.get("poids_sec")} if roles.voit_medical(u["role"]) else {}))
    return lignes


@routeur.post("/patients")
def creer(corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_IDENTITE))):
    """Crée un patient. Doublon probable (même nom, prénom, naissance) : 409 sauf si « forcer » est vrai."""
    d = _identite(corps, True)
    n, pn = validation.normaliser(d["nom"]), validation.normaliser(d["prenom"])
    if not corps.get("forcer") and db.base().patients.find_one({"nom_norm": n, "prenom_norm": pn, "date_naissance": d["date_naissance"]}):
        raise HTTPException(409, "DOUBLON : un patient de même nom, prénom et date de naissance existe déjà")
    doc = {"id": str(uuid.uuid4()), "code": prochain_code(), **d, "nom_norm": n, "prenom_norm": pn, "statut": "actif",
           "created_at": db.maintenant(), "cree_par": u["login"], "updated_at": db.maintenant(), "maj_par": u["login"]}
    if roles.voit_medical(u["role"]):
        doc.update(_medical({k: v for k, v in corps.items() if k != "statut"}))
    db.base().patients.insert_one(doc)
    historique.noter("patients", doc["id"], u, [], "creation")
    journaliser("patient_cree", u, doc["code"])
    return masquer(doc, u["role"])


def _patient(id_: str) -> dict:
    p = db.base().patients.find_one({"id": id_})
    if not p:
        raise HTTPException(404, "Patient introuvable")
    return p


@routeur.get("/patients/{id_}")
def lire(id_: str, u: dict = Depends(exiger_roles(roles.LECTURE_PATIENT))):
    """Dossier d'un patient (ouverture journalisée : qui a consulté quel dossier)."""
    p = _patient(id_)
    journaliser("patient_lu", u, p["code"])
    return masquer(p, u["role"])


@routeur.put("/patients/{id_}")
def modifier(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_IDENTITE))):
    """
    Modifie un patient. L'identité : accueil et soignants ; le médical : soignants et administration (sinon 403) ;
    la prescription : médecin seulement ; la suppression d'un statut « actif » vers « décédé » etc. passe par le champ « statut ».
    """
    p = _patient(id_)
    maj = _identite(corps, False)
    if CHAMPS_MEDICAUX & set(corps) - {"prescription", "acces_vasculaires"} or "statut" in corps:
        if u["role"] not in roles.ECRITURE_MEDICAL:
            raise HTTPException(403, "Droits insuffisants pour modifier le dossier médical")
        maj.update(_medical(corps))
    if "prescription" in corps:
        if u["role"] not in roles.PRESCRIPTION:
            raise HTTPException(403, "Seul le médecin prescrit la dialyse")
        maj["prescription"] = valider_prescription(corps.get("prescription") or {})
    if "nom" in maj or "prenom" in maj:
        maj["nom_norm"] = validation.normaliser(maj.get("nom", p["nom"]))
        maj["prenom_norm"] = validation.normaliser(maj.get("prenom", p["prenom"]))
    changes = historique.champs_modifies(p, maj)
    if changes:
        maj.update({"updated_at": db.maintenant(), "maj_par": u["login"]})
        db.base().patients.update_one({"id": id_}, {"$set": maj})
        historique.noter("patients", id_, u, changes)
        journaliser("patient_modifie", u, f"{p['code']} : {', '.join(sorted(changes))}")
    return masquer(db.base().patients.find_one({"id": id_}), u["role"])


@routeur.put("/patients/{id_}/pieces")
def maj_pieces(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_IDENTITE))):
    """Met à jour la RÉCEPTION des pièces du dossier d'adhésion (pièces du MODÈLE du patient) : {cle: {statut, date, note}}. Jamais le contenu des pièces."""
    p = _patient(id_)
    modele = adhesion.modele_de(p, adhesion.dictionnaire())
    connues = {x["cle"]: x for x in modele["pieces"]}
    pieces = dict(p.get("pieces_admission") or {})
    for cle, v in (corps or {}).items():
        if cle not in connues or not isinstance(v, dict):
            raise HTTPException(422, f"Pièce inconnue pour ce modèle : {cle}")
        statut = validation.choix(v, "statut", "État de la pièce", adhesion.ETATS_PIECE, obligatoire=True)
        if statut == "sans_objet" and connues[cle]["obligatoire"]:
            raise HTTPException(422, "Une pièce obligatoire ne peut pas être « sans objet »")
        pieces[cle] = {"statut": statut, "date": validation.date_iso(v, "date", "Date de réception", False, futur_ok=False) if statut == "recue" else "",
                       "note": validation.texte(v, "note", "Remarque", False, 200), "par": u["login"]}
    db.base().patients.update_one({"id": id_}, {"$set": {"pieces_admission": pieces, "updated_at": db.maintenant(), "maj_par": u["login"]}})
    historique.noter("patients", id_, u, ["pieces_admission"])
    journaliser("pieces_adhesion_modifiees", u, p["code"])
    return masquer(db.base().patients.find_one({"id": id_}), u["role"])


@routeur.put("/patients/{id_}/modele-adhesion")
def changer_modele(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_IDENTITE))):
    """Rattache le patient à un autre modèle de dossier d'adhésion (variante d'un centre). Les pièces déjà reçues et de même clé sont conservées."""
    p = _patient(id_)
    if not any(m["id"] == corps.get("modele_id") for m in adhesion.tous()):
        raise HTTPException(422, "Modèle inconnu")
    db.base().patients.update_one({"id": id_}, {"$set": {"modele_adhesion_id": corps["modele_id"], "updated_at": db.maintenant(), "maj_par": u["login"]}})
    historique.noter("patients", id_, u, ["modele_adhesion"])
    journaliser("modele_adhesion_patient", u, p["code"])
    return masquer(db.base().patients.find_one({"id": id_}), u["role"])


@routeur.post("/patients/{id_}/acces")
def ajouter_acces(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_MEDICAL))):
    """Ajoute un accès vasculaire (fistule, cathéter…). Un seul accès « principal » actif à la fois par défaut (le plus récent)."""
    p = _patient(id_)
    a = {"id": str(uuid.uuid4()), "type": validation.choix(corps, "type", "Type d'accès", TYPES_ACCES, obligatoire=True),
         "localisation": validation.texte(corps, "localisation", "Localisation (ex. bras gauche)", True, 80),
         "date_pose": validation.date_iso(corps, "date_pose", "Date de pose", False, futur_ok=False),
         "remarques": validation.texte(corps, "remarques", "Remarques", False, 300), "actif": True, "date_retrait": ""}
    db.base().patients.update_one({"id": id_}, {"$push": {"acces_vasculaires": a}, "$set": {"updated_at": db.maintenant(), "maj_par": u["login"]}})
    historique.noter("patients", id_, u, ["acces_vasculaires"])
    journaliser("acces_ajoute", u, p["code"])
    return a


@routeur.put("/patients/{id_}/acces/{aid}")
def modifier_acces(id_: str, aid: str, corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_MEDICAL))):
    """Modifie un accès, ou le retire (actif=false : date de retrait posée, l'historique des séances reste cohérent)."""
    p = _patient(id_)
    acces = p.get("acces_vasculaires") or []
    cible = next((a for a in acces if a["id"] == aid), None)
    if not cible:
        raise HTTPException(404, "Accès introuvable")
    if "type" in corps:
        cible["type"] = validation.choix(corps, "type", "Type d'accès", TYPES_ACCES, obligatoire=True)
    for cle, lib in (("localisation", "Localisation"), ("remarques", "Remarques")):
        if cle in corps:
            cible[cle] = validation.texte(corps, cle, lib, cle == "localisation", 300)
    if "date_pose" in corps:
        cible["date_pose"] = validation.date_iso(corps, "date_pose", "Date de pose", False, futur_ok=False)
    if "actif" in corps:
        cible["actif"] = bool(corps["actif"])
        cible["date_retrait"] = "" if cible["actif"] else (validation.date_iso(corps, "date_retrait", "Date de retrait") or db.maintenant()[:10])
    db.base().patients.update_one({"id": id_}, {"$set": {"acces_vasculaires": acces, "updated_at": db.maintenant(), "maj_par": u["login"]}})
    historique.noter("patients", id_, u, ["acces_vasculaires"])
    journaliser("acces_modifie", u, p["code"])
    return cible


@routeur.delete("/patients/{id_}")
def supprimer(id_: str, u: dict = Depends(exiger_roles(roles.SUPPRESSION))):
    """Supprime un patient SANS séance (saisie par erreur). Sinon : changer son statut. Administration seulement, journalisé."""
    p = _patient(id_)
    if db.base().seances.count_documents({"patient_id": id_}) > 0:
        raise HTTPException(409, "Ce patient a des séances : changez son statut au lieu de le supprimer")
    db.base().patients.delete_one({"id": id_})
    journaliser("patient_supprime", u, p["code"])
    return {"ok": True}
