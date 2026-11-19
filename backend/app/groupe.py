"""
Vue du GROUPE (tous les centres) : synthèse consolidée pour le directeur général et le super administrateur, et transfert d'un patient d'un centre à l'autre.

Ces routes sont les SEULES à franchir la frontière entre centres, donc réservées aux comptes du groupe (super administrateur, directeur général sans centre).
La synthèse est AGRÉGÉE (jamais de nom ni de code patient) ; le transfert exige le super administrateur, le consentement du patient et est journalisé dans les DEUX centres.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from . import db, patients, rapports, roles, validation
from .auth import exiger_roles, journaliser, utilisateur_courant

routeur = APIRouter()

MOTIFS_TRANSFERT = ["Déménagement du patient", "Demande du patient", "Raison médicale", "Rapprochement familial", "Autre"]


def _compte_du_groupe(u: dict = Depends(exiger_roles(roles.ROLES_GROUPE))) -> dict:
    """Refuse (403) un compte rattaché à un centre, même de rôle « direction » : seule la vue de groupe franchit les centres."""
    if not u["groupe"]:
        raise HTTPException(403, "Réservé aux comptes du groupe (sans centre)")
    return u


def _synthese_centre(centre: dict, du: str, au: str) -> dict:
    """Indicateurs d'UN centre sur la période : le centre courant de la requête est fixé le temps du calcul, puis rétabli."""
    ancien = db.centre_courant.get()
    db.fixer_centre(centre["id"])
    try:
        seances, _ = rapports._donnees(du, au)
        i = rapports.indicateurs(seances)
        factures = list(db.base().factures.find({"date": {"$gte": du, "$lte": au}, "annulee": {"$ne": True}}, {"_id": 0, "total": 1, "paiements": 1}))
        facture = sum(int(f.get("total", 0)) for f in factures)
        encaisse = sum(int(p.get("montant", 0)) for f in factures for p in f.get("paiements", []))
        return {"id": centre["id"], "nom": centre["nom"], "actif": centre.get("actif", True), "realisees": i["realisees"], "absents": i["absents"], "annulees": i["annulees"],
                "patients": i["patients"], "incidents": i["incidents"], "taux_absence_pct": i["taux_absence_pct"], "ktv_moyen": i["ktv_moyen"],
                "patients_actifs": db.base().patients.count_documents({"statut": "actif"}), "facture": facture, "encaisse": encaisse}
    finally:
        db.fixer_centre(ancien)


@routeur.get("/groupe/synthese")
def synthese(du: str, au: str, u: dict = Depends(_compte_du_groupe)):
    """Synthèse de TOUS les centres sur une période : une ligne par centre + totaux (taux recalculés sur les totaux, jamais additionnés)."""
    du, au = rapports._periode(du, au)
    lignes = [_synthese_centre(c, du, au) for c in db.brut().centres.find({}, {"_id": 0, "logo": 0}).sort("nom", 1)]
    total = {k: sum(l[k] for l in lignes) for k in ("realisees", "absents", "annulees", "patients", "incidents", "patients_actifs", "facture", "encaisse")}
    total["taux_absence_pct"] = round(100 * total["absents"] / (total["realisees"] + total["absents"]), 1) if (total["realisees"] or total["absents"]) else 0.0
    journaliser("synthese_groupe_consultee", u, f"{du} → {au}")
    return {"du": du, "au": au, "centres": lignes, "total": total}


@routeur.post("/patients/{id_}/transfert")
def transferer(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """
    Transfère un patient du centre de travail vers un autre centre. Le DOSSIER suit (identité, dossier médical, prescription sans poste, accès vasculaires, pièces d'adhésion, bilans) :
    il est COPIÉ dans le centre d'arrivée avec un nouveau code. L'historique d'activité (séances, factures) reste dans le centre de départ, où le patient passe « Transféré »
    et où ses séances à venir sont annulées. Exige le consentement du patient et un motif ; journalisé dans les deux centres.
    """
    if not u["centre_id"]:
        raise HTTPException(400, "Choisissez d'abord le centre de départ")
    if corps.get("consentement") is not True:
        validation.erreur("Le consentement du patient au transfert de son dossier est obligatoire")
    motif = validation.choix(corps, "motif", "Motif du transfert", MOTIFS_TRANSFERT, obligatoire=True)
    precision = validation.texte(corps, "precision", "Précision", False, 200)
    arrivee = db.brut().centres.find_one({"id": str(corps.get("centre_destination_id") or "")})
    if not arrivee:
        validation.erreur("Centre d'arrivée inconnu")
    if arrivee["id"] == u["centre_id"]:
        validation.erreur("Le centre d'arrivée doit être différent du centre de départ")
    if not arrivee.get("actif", True):
        validation.erreur("Le centre d'arrivée est désactivé")
    p = patients._patient(id_)
    if p.get("statut") in ("transfere", "decede"):
        raise HTTPException(409, "Ce patient n'est plus suivi dans ce centre")
    depart = db.brut().centres.find_one({"id": u["centre_id"]})
    maintenant = db.maintenant()
    # --- Code du patient dans le centre d'arrivée (compteur propre à ce centre) ---
    from pymongo import ReturnDocument
    c = db.brut().parametres.find_one_and_update({"id": "compteur_patients", "centre_id": arrivee["id"]}, {"$inc": {"n": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    code = f"{arrivee['prefixe']}-{int(c['n']):06d}"
    # --- Copie du dossier dans le centre d'arrivée (rien d'attaché au centre de départ : poste, modèle d'adhésion, organisme de prise en charge) ---
    neuf = {k: v for k, v in p.items() if k not in ("_id", "id", "code", "centre_id", "modele_adhesion_id", "organisme_id")}
    if isinstance(neuf.get("prescription"), dict):
        neuf["prescription"] = {k: v for k, v in neuf["prescription"].items() if k != "poste_id"}
    neuf.update({"id": str(uuid.uuid4()), "code": code, "centre_id": arrivee["id"], "statut": "actif", "created_at": maintenant, "cree_par": u["login"],
                 "updated_at": maintenant, "maj_par": u["login"],
                 "transfere_de": {"centre_id": depart["id"], "centre_nom": depart["nom"], "code": p["code"], "le": maintenant, "motif": motif}})
    db.brut().patients.insert_one(neuf)
    # --- Bilans biologiques : copiés (historique clinique utile au nouveau centre) ---
    bilans = [{k: v for k, v in b.items() if k != "_id"} | {"id": str(uuid.uuid4()), "patient_id": neuf["id"], "centre_id": arrivee["id"]}
              for b in db.base().bilans.find({"patient_id": p["id"]})]
    if bilans:
        db.brut().bilans.insert_many(bilans)
    # --- Centre de départ : statut « transféré », séances à venir annulées ---
    annulees = db.base().seances.update_many({"patient_id": p["id"], "statut": "planifiee"}, {"$set": {"statut": "annulee", "motif": "Transfert vers un autre centre", "updated_at": maintenant}}).modified_count
    db.base().patients.update_one({"id": p["id"]}, {"$set": {"statut": "transfere", "updated_at": maintenant, "maj_par": u["login"],
                                                              "transfere_vers": {"centre_id": arrivee["id"], "centre_nom": arrivee["nom"], "code": code, "le": maintenant, "motif": motif}}})
    detail = f"{p['code']} → {arrivee['nom']} ({code}) · motif : {motif}" + (f" · {precision}" if precision else "")
    journaliser("patient_transfere_depart", u, detail)
    db.brut().journal.insert_one({"quand": maintenant, "action": "patient_transfere_arrivee", "acteur_id": u["id"], "acteur": u["login"], "role": u["role"],
                                  "detail": f"{code} ← {depart['nom']} ({p['code']}) · motif : {motif}", "centre_id": arrivee["id"]})
    return {"ok": True, "code_arrivee": code, "centre_arrivee": arrivee["nom"], "bilans_copies": len(bilans), "seances_annulees": annulees}
