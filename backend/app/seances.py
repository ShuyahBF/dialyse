"""
Séances de dialyse : planning, déroulement (constantes, incidents), clôture, validation par le médecin.

Cycle de vie : planifiee → en_cours → terminee → (validée par le médecin : verrouillée)  ·  planifiee → annulee | absente.
Un poste ne reçoit qu'une séance par créneau ; un patient n'a qu'une séance par créneau et par jour.
Le secrétariat voit le planning (qui, quand, où) mais JAMAIS le détail médical (constantes, incidents, alertes).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from . import alertes as al, db, historique, patients as pat, roles, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()
STATUTS = ["planifiee", "en_cours", "terminee", "annulee", "absente"]
LIBELLE_STATUT = {"planifiee": "Planifiée", "en_cours": "En cours", "terminee": "Terminée", "annulee": "Annulée", "absente": "Patient absent"}
TYPES_INCIDENT = ["Hypotension", "Crampes", "Nausées / vomissements", "Céphalées", "Douleur thoracique", "Saignement du point de ponction",
                  "Problème d'accès vasculaire", "Coagulation du circuit", "Alarme machine", "Fièvre / frissons", "Réaction allergique", "Autre"]
CRENEAU_HEURE = {"matin": "07:00", "midi": "12:00", "soir": "17:00"}
MAX_JOURS_GENERATION = 31


def _public(s: dict, patient: dict | None, poste: dict | None, role: str) -> dict:
    """Séance prête à l'affichage : patient et poste joints ; sans détail médical pour le secrétariat."""
    d = {k: v for k, v in s.items() if k != "_id"}
    d["statut_libelle"] = LIBELLE_STATUT.get(d["statut"], d["statut"])
    d["patient"] = {"id": s["patient_id"], "code": (patient or {}).get("code", ""), "nom": (patient or {}).get("nom", "?"),
                    "prenom": (patient or {}).get("prenom", "")}
    d["poste_nom"] = (poste or {}).get("nom", "?")
    d["poste_isolement"] = bool((poste or {}).get("isolement"))
    if roles.voit_medical(role):
        d["alertes"] = al.alertes_seance(s, (patient or {}).get("poids_sec"))
        d["poids_sec"] = (patient or {}).get("poids_sec")
        d["serologie_positive"] = any(v == "positif" for v in ((patient or {}).get("serologies") or {}).values())
    else:
        for k in ("pre", "post", "parametres", "surveillance", "incidents", "observations", "acces_id"):
            d.pop(k, None)
    return d


def _joindre(seances: list[dict], role: str) -> list[dict]:
    """Joint patients et postes EN BLOC (une lecture par collection, jamais une par ligne : règle 7)."""
    pids = list({s["patient_id"] for s in seances})
    oids = list({s["poste_id"] for s in seances})
    pm = {p["id"]: p for p in db.base().patients.find({"id": {"$in": pids}})} if pids else {}
    om = {p["id"]: p for p in db.base().postes.find({"id": {"$in": oids}})} if oids else {}
    return [_public(s, pm.get(s["patient_id"]), om.get(s["poste_id"]), role) for s in seances]


def _seance(id_: str) -> dict:
    s = db.base().seances.find_one({"id": id_})
    if not s:
        raise HTTPException(404, "Séance introuvable")
    return s


def _poste_libre(poste_id: str, jour: str, creneau: str, sauf: str = "") -> bool:
    """Vrai si aucune séance non annulée n'occupe ce poste à ce créneau."""
    f = {"poste_id": poste_id, "date": jour, "creneau": creneau, "statut": {"$nin": ["annulee", "absente"]}}
    if sauf:
        f["id"] = {"$ne": sauf}
    return db.base().seances.find_one(f) is None


def _patient_libre(patient_id: str, jour: str, creneau: str, sauf: str = "") -> bool:
    f = {"patient_id": patient_id, "date": jour, "creneau": creneau, "statut": {"$nin": ["annulee", "absente"]}}
    if sauf:
        f["id"] = {"$ne": sauf}
    return db.base().seances.find_one(f) is None


@routeur.get("/seances/listes")
def listes(u: dict = Depends(exiger_roles(roles.LECTURE_SEANCE))):
    """Listes finies : statuts, créneaux, types d'incident."""
    return {"statuts": [{"valeur": s, "libelle": LIBELLE_STATUT[s]} for s in STATUTS], "creneaux": pat.CRENEAUX, "incidents": TYPES_INCIDENT,
            "heures_creneaux": CRENEAU_HEURE}


@routeur.get("/seances")
def lister(date_: str = "", du: str = "", au: str = "", patient_id: str = "", poste_id: str = "", statut: str = "",
           u: dict = Depends(exiger_roles(roles.LECTURE_SEANCE))):
    """Séances filtrées (une date, ou une période du/au, patient, poste, statut). Ordre : date, créneau, poste."""
    f: dict = {}
    if date_:
        f["date"] = validation.date_iso({"d": date_}, "d", "Date")
    elif du or au:
        f["date"] = {}
        if du:
            f["date"]["$gte"] = validation.date_iso({"d": du}, "d", "Du")
        if au:
            f["date"]["$lte"] = validation.date_iso({"d": au}, "d", "Au")
    for cle, v in (("patient_id", patient_id), ("poste_id", poste_id), ("statut", statut)):
        if v:
            f[cle] = v
    seances = list(db.base().seances.find(f).sort([("date", 1), ("creneau", 1), ("poste_id", 1)]).limit(3000))
    ordre = {c: i for i, c in enumerate(pat.CRENEAUX)}
    res = _joindre(seances, u["role"])
    res.sort(key=lambda s: (s["date"], ordre.get(s["creneau"], 9), s["poste_nom"]))
    return res


@routeur.get("/seances/{id_}")
def lire(id_: str, u: dict = Depends(exiger_roles(roles.LECTURE_SEANCE))):
    """Une séance. L'ouverture du détail médical est journalisée."""
    s = _seance(id_)
    if roles.voit_medical(u["role"]):
        journaliser("seance_lue", u, id_)
    return _joindre([s], u["role"])[0]


def _creer(corps: dict, u: dict, source: str = "manuel") -> tuple[dict, list[str]]:
    """Planifie une séance après contrôles (patient actif, poste en service, créneau libre). Renvoie la séance et les alertes de planification."""
    jour = validation.date_iso(corps, "date", "Date", True)
    creneau = validation.choix(corps, "creneau", "Créneau", pat.CRENEAUX, obligatoire=True)
    p = db.base().patients.find_one({"id": str(corps.get("patient_id", ""))})
    if not p:
        raise HTTPException(404, "Patient introuvable")
    if p.get("statut") != "actif":
        raise HTTPException(409, "Ce patient n'est pas en dialyse active (statut : " + pat.LIBELLE_STATUT.get(p.get("statut", ""), "?") + ")")
    poste = db.base().postes.find_one({"id": str(corps.get("poste_id", ""))})
    if not poste:
        raise HTTPException(404, "Poste introuvable")
    if poste.get("statut") != "actif":
        raise HTTPException(409, "Ce poste n'est pas en service")
    if not _poste_libre(poste["id"], jour, creneau):
        raise HTTPException(409, "Ce poste est déjà occupé à ce créneau")
    if not _patient_libre(p["id"], jour, creneau):
        raise HTTPException(409, "Ce patient a déjà une séance à ce créneau")
    prevenir = []
    a = al.alerte_isolement(p.get("serologies"), bool(poste.get("isolement")))
    if a:
        prevenir.append(a)
    doc = {"id": str(uuid.uuid4()), "patient_id": p["id"], "poste_id": poste["id"], "date": jour, "creneau": creneau,
           "heure_prevue": validation.heure(corps, "heure_prevue", "Heure prévue") or CRENEAU_HEURE[creneau], "statut": "planifiee",
           "source": source, "created_at": db.maintenant(), "cree_par": u["login"], "updated_at": db.maintenant(), "maj_par": u["login"]}
    db.base().seances.insert_one(doc)
    journaliser("seance_planifiee", u, f"{p['code']} {jour} {creneau} {poste['nom']}")
    return doc, prevenir


@routeur.post("/seances")
def planifier(corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    """Planifie une séance. Réponse : la séance + « alertes_planification » (ex. sérologie positive sur un poste non isolé)."""
    doc, prevenir = _creer(corps, u)
    return _joindre([doc], u["role"])[0] | {"alertes_planification": prevenir}


@routeur.post("/seances/generer")
def generer(corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    """
    Génère le planning d'une période (31 jours au plus) d'après les PRESCRIPTIONS (jours et créneau) des patients actifs.
    Règles : poste en service et libre ; patient à sérologie positive = poste d'isolement uniquement ; autres = postes ordinaires d'abord.
    Réponse : séances créées, déjà existantes (ignorées), et non placées (avec la raison).
    """
    du = date.fromisoformat(validation.date_iso(corps, "du", "Du", True))
    au = date.fromisoformat(validation.date_iso(corps, "au", "Au", True))
    if au < du or (au - du).days >= MAX_JOURS_GENERATION:
        validation.erreur(f"Période invalide (de 1 à {MAX_JOURS_GENERATION} jours)")
    postes = list(db.base().postes.find({"statut": "actif"}).sort("nom", 1))
    patients = [p for p in db.base().patients.find({"statut": "actif", "prescription.jours.0": {"$exists": True}}).sort("nom_norm", 1)]
    # Occupation existante de la période, lue EN BLOC.
    existantes = list(db.base().seances.find({"date": {"$gte": du.isoformat(), "$lte": au.isoformat()}, "statut": {"$nin": ["annulee", "absente"]}}))
    postes_pris = {(s["date"], s["creneau"], s["poste_id"]) for s in existantes}
    patients_pris = {(s["date"], s["creneau"], s["patient_id"]) for s in existantes}
    crees, ignorees, non_placees = [], 0, []
    jour = du
    while jour <= au:
        nom_jour = pat.JOURS[jour.weekday()]
        for p in patients:
            presc = p.get("prescription") or {}
            if nom_jour not in presc.get("jours", []) or presc.get("creneau") not in pat.CRENEAUX:
                continue
            c, iso = presc["creneau"], jour.isoformat()
            if (iso, c, p["id"]) in patients_pris:
                ignorees += 1
                continue
            positif = any(v == "positif" for v in (p.get("serologies") or {}).values())
            candidats = [o for o in postes if (iso, c, o["id"]) not in postes_pris]
            if positif:
                candidats = [o for o in candidats if o.get("isolement")]
            else:
                candidats.sort(key=lambda o: bool(o.get("isolement")))       # postes ordinaires d'abord (sort stable)
            if not candidats:
                non_placees.append({"patient": f"{p['nom']} {p['prenom']}", "code": p["code"], "date": iso, "creneau": c,
                                    "raison": "aucun poste d'isolement libre" if positif else "aucun poste libre"})
                continue
            doc, _ = _creer({"patient_id": p["id"], "poste_id": candidats[0]["id"], "date": iso, "creneau": c}, u, "generation")
            postes_pris.add((iso, c, candidats[0]["id"]))
            patients_pris.add((iso, c, p["id"]))
            crees.append(doc["id"])
        jour += timedelta(days=1)
    journaliser("planning_genere", u, f"{du} → {au} : {len(crees)} créées, {len(non_placees)} non placées")
    return {"creees": len(crees), "deja_existantes": ignorees, "non_placees": non_placees}


@routeur.put("/seances/{id_}")
def deplacer(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    """Déplace une séance planifiée (date, créneau, poste, heure) ; mêmes contrôles qu'à la création."""
    s = _seance(id_)
    if s["statut"] != "planifiee":
        raise HTTPException(409, "Seule une séance planifiée peut être déplacée")
    jour = validation.date_iso(corps, "date", "Date") or s["date"]
    creneau = validation.choix(corps, "creneau", "Créneau", pat.CRENEAUX) or s["creneau"]
    poste_id = str(corps.get("poste_id") or s["poste_id"])
    poste = db.base().postes.find_one({"id": poste_id})
    if not poste or poste.get("statut") != "actif":
        raise HTTPException(409, "Poste introuvable ou hors service")
    if not _poste_libre(poste_id, jour, creneau, id_):
        raise HTTPException(409, "Ce poste est déjà occupé à ce créneau")
    if not _patient_libre(s["patient_id"], jour, creneau, id_):
        raise HTTPException(409, "Ce patient a déjà une séance à ce créneau")
    maj = {"date": jour, "creneau": creneau, "poste_id": poste_id, "heure_prevue": validation.heure(corps, "heure_prevue", "Heure prévue") or s["heure_prevue"],
           "updated_at": db.maintenant(), "maj_par": u["login"]}
    ch = historique.champs_modifies(s, maj)
    db.base().seances.update_one({"id": id_}, {"$set": maj})
    historique.noter("seances", id_, u, ch)
    journaliser("seance_deplacee", u, id_)
    p = db.base().patients.find_one({"id": s["patient_id"]})
    a = al.alerte_isolement((p or {}).get("serologies"), bool(poste.get("isolement")))
    return _joindre([db.base().seances.find_one({"id": id_})], u["role"])[0] | {"alertes_planification": [a] if a else []}


@routeur.post("/seances/{id_}/annuler")
def annuler(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.PLANNING))):
    """Annule une séance planifiée, ou la marque « patient absent » (motif obligatoire pour l'annulation)."""
    s = _seance(id_)
    if s["statut"] != "planifiee":
        raise HTTPException(409, "Seule une séance planifiée peut être annulée")
    absent = bool(corps.get("absent"))
    motif = validation.texte(corps, "motif", "Motif", not absent, 300)
    db.base().seances.update_one({"id": id_}, {"$set": {"statut": "absente" if absent else "annulee", "motif": motif,
                                                        "updated_at": db.maintenant(), "maj_par": u["login"]}})
    historique.noter("seances", id_, u, ["statut"])
    journaliser("seance_absente" if absent else "seance_annulee", u, id_)
    return _joindre([db.base().seances.find_one({"id": id_})], u["role"])[0]


def _constantes(c: dict, avec_poids: bool = True) -> dict:
    """Constantes validées : poids, tension, pouls, température (plages plausibles pour attraper les fautes de frappe)."""
    d = {"tension_sys": validation.nombre(c, "tension_sys", "Tension systolique", 40, 280),
         "tension_dia": validation.nombre(c, "tension_dia", "Tension diastolique", 20, 160),
         "pouls": validation.nombre(c, "pouls", "Pouls", 20, 220),
         "temperature": validation.nombre(c, "temperature", "Température", 33, 43)}
    if avec_poids:
        d["poids"] = validation.nombre(c, "poids", "Poids (kg)", 20, 250)
    if d["tension_sys"] is not None and d["tension_dia"] is not None and d["tension_dia"] >= d["tension_sys"]:
        validation.erreur("La tension diastolique doit être inférieure à la systolique")
    return d


@routeur.post("/seances/{id_}/demarrer")
def demarrer(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.DEROULEMENT))):
    """
    Démarre la séance : constantes de début (poids et tension obligatoires) et paramètres de la machine.
    Les paramètres non fournis reprennent la prescription du patient. Le poste doit être en service.
    """
    s = _seance(id_)
    if s["statut"] != "planifiee":
        raise HTTPException(409, "Seule une séance planifiée peut être démarrée")
    pre = {**_constantes(corps.get("pre") or {}), "symptomes": validation.texte(corps.get("pre") or {}, "symptomes", "Symptômes", False, 300)}
    if pre["poids"] is None or pre["tension_sys"] is None or pre["tension_dia"] is None:
        validation.erreur("Poids et tension de début de séance obligatoires")
    poste = db.base().postes.find_one({"id": s["poste_id"]})
    if not poste or poste.get("statut") != "actif":
        raise HTTPException(409, "Le poste n'est pas en service")
    p = db.base().patients.find_one({"id": s["patient_id"]}) or {}
    presc, entree = p.get("prescription") or {}, corps.get("parametres") or {}
    acces_id = str(entree.get("acces_id") or "")
    if acces_id and not any(a["id"] == acces_id and a.get("actif", True) for a in p.get("acces_vasculaires") or []):
        validation.erreur("Accès vasculaire inconnu ou retiré")
    param = {"duree_prevue_min": validation.nombre(entree, "duree_prevue_min", "Durée prévue", 30, 600) or presc.get("duree_min"),
             "dialyseur": validation.texte(entree, "dialyseur", "Dialyseur", False, 80) or presc.get("dialyseur", ""),
             "debit_sang": validation.nombre(entree, "debit_sang", "Débit sang", 100, 600) or presc.get("debit_sang"),
             "debit_dialysat": validation.nombre(entree, "debit_dialysat", "Débit dialysat", 300, 800) or presc.get("debit_dialysat"),
             "anticoagulation": validation.texte(entree, "anticoagulation", "Anticoagulation", False, 60) or presc.get("anticoagulation", ""),
             "heparine_ui": validation.nombre(entree, "heparine_ui", "Héparine", 0, 20000) if entree.get("heparine_ui") not in (None, "") else presc.get("heparine_ui"),
             "uf_prevue_l": validation.nombre(entree, "uf_prevue_l", "Ultrafiltration prévue (l)", 0, 10), "acces_id": acces_id}
    maj = {"statut": "en_cours", "pre": pre, "parametres": param, "debut_a": db.maintenant(), "infirmier": u["login"],
           "surveillance": [], "incidents": [], "updated_at": db.maintenant(), "maj_par": u["login"]}
    db.base().seances.update_one({"id": id_}, {"$set": maj})
    historique.noter("seances", id_, u, ["statut"])
    journaliser("seance_demarree", u, id_)
    return _joindre([db.base().seances.find_one({"id": id_})], u["role"])[0]


def _en_cours(id_: str) -> dict:
    s = _seance(id_)
    if s["statut"] != "en_cours":
        raise HTTPException(409, "La séance n'est pas en cours")
    return s


@routeur.post("/seances/{id_}/surveillance")
def surveiller(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.DEROULEMENT))):
    """Ajoute un relevé de surveillance (tension, pouls, pressions, ultrafiltration cumulée, débit)."""
    _en_cours(id_)
    m = {"id": str(uuid.uuid4()), "heure": validation.heure(corps, "heure", "Heure") or db.maintenant()[11:16], **_constantes(corps, False),
         "pression_veineuse": validation.nombre(corps, "pression_veineuse", "Pression veineuse", -100, 500),
         "uf_cumule_l": validation.nombre(corps, "uf_cumule_l", "UF cumulée (l)", 0, 10),
         "debit_sang": validation.nombre(corps, "debit_sang", "Débit sang", 100, 600),
         "remarque": validation.texte(corps, "remarque", "Remarque", False, 200), "par": u["login"]}
    db.base().seances.update_one({"id": id_}, {"$push": {"surveillance": m}, "$set": {"updated_at": db.maintenant(), "maj_par": u["login"]}})
    journaliser("surveillance_ajoutee", u, id_)
    return _joindre([db.base().seances.find_one({"id": id_})], u["role"])[0]


@routeur.post("/seances/{id_}/incident")
def incident(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.DEROULEMENT))):
    """Déclare un incident (liste finie + description et conduite tenue)."""
    _en_cours(id_)
    i = {"id": str(uuid.uuid4()), "heure": validation.heure(corps, "heure", "Heure") or db.maintenant()[11:16],
         "type": validation.choix(corps, "type", "Type d'incident", TYPES_INCIDENT, obligatoire=True),
         "description": validation.texte(corps, "description", "Description", False, 500),
         "conduite": validation.texte(corps, "conduite", "Conduite tenue", False, 500), "par": u["login"]}
    db.base().seances.update_one({"id": id_}, {"$push": {"incidents": i}, "$set": {"updated_at": db.maintenant(), "maj_par": u["login"]}})
    journaliser("incident_declare", u, f"{id_} ({i['type']})")
    return _joindre([db.base().seances.find_one({"id": id_})], u["role"])[0]


@routeur.post("/seances/{id_}/terminer")
def terminer(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.DEROULEMENT))):
    """Termine la séance : constantes de fin (poids obligatoire), volume d'ultrafiltration, Kt/V, durée réelle."""
    s = _en_cours(id_)
    post = {**_constantes(corps.get("post") or {}),
            "volume_uf_l": validation.nombre(corps.get("post") or {}, "volume_uf_l", "Volume d'ultrafiltration (l)", 0, 10),
            "kt_v": validation.nombre(corps.get("post") or {}, "kt_v", "Kt/V", 0, 3),
            "duree_reelle_min": validation.nombre(corps.get("post") or {}, "duree_reelle_min", "Durée réelle (min)", 10, 720)}
    if post["poids"] is None:
        validation.erreur("Poids de fin de séance obligatoire")
    if post["duree_reelle_min"] is None:       # durée réelle déduite du début si elle n'est pas saisie
        from datetime import datetime
        try:
            post["duree_reelle_min"] = round((datetime.fromisoformat(db.maintenant()) - datetime.fromisoformat(s["debut_a"])).total_seconds() / 60)
        except Exception:
            post["duree_reelle_min"] = None
    maj = {"statut": "terminee", "post": post, "fin_a": db.maintenant(), "observations": validation.texte(corps, "observations", "Observations", False, 1000),
           "updated_at": db.maintenant(), "maj_par": u["login"]}
    db.base().seances.update_one({"id": id_}, {"$set": maj})
    historique.noter("seances", id_, u, ["statut"])
    journaliser("seance_terminee", u, id_)
    return _joindre([db.base().seances.find_one({"id": id_})], u["role"])[0]


@routeur.post("/seances/{id_}/valider")
def valider(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.VALIDATION_SEANCE))):
    """Le médecin valide une séance terminée : elle est alors verrouillée (aucune modification ultérieure)."""
    s = _seance(id_)
    if s["statut"] != "terminee":
        raise HTTPException(409, "Seule une séance terminée peut être validée")
    if s.get("validee_par"):
        raise HTTPException(409, "Séance déjà validée")
    db.base().seances.update_one({"id": id_}, {"$set": {"validee_par": u["login"], "validee_le": db.maintenant(),
                                                        "avis_medecin": validation.texte(corps, "avis", "Avis du médecin", False, 500),
                                                        "updated_at": db.maintenant(), "maj_par": u["login"]}})
    historique.noter("seances", id_, u, ["validation"])
    journaliser("seance_validee", u, id_)
    return _joindre([db.base().seances.find_one({"id": id_})], u["role"])[0]
