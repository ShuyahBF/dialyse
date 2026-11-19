"""
Facturation et prise en charge (montants en FCFA, entiers).

  - TARIFS : actes facturables ; ceux marqués « automatique » sont ajoutés à la facture de chaque séance ;
  - ORGANISMES payeurs (assurance, mutuelle, employeur, prise en charge sociale) avec un taux de prise en charge ;
    un patient peut avoir son propre taux (sinon celui de son organisme, sinon 0 % : paiement direct) ;
  - FACTURES : une par séance terminée, avec la répartition part organisme / part patient figée à la création
    (nom du patient, de l'organisme et prix sont COPIÉS : une facture émise ne change plus) ;
  - PAIEMENTS : par le patient ou par l'organisme, partiels possibles, jamais au-delà du reste dû ;
  - une facture n'est jamais supprimée : elle s'ANNULE (administration, motif obligatoire, aucun paiement enregistré).
Aucune donnée médicale n'apparaît sur une facture.
"""
from __future__ import annotations

import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from . import db, roles, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()

TYPES_ORGANISME = ["Assurance maladie", "Mutuelle / assurance privée", "Employeur", "Prise en charge sociale", "Autre"]
MODES_PAIEMENT = ["Espèces", "Orange Money", "Moov Money", "Virement bancaire", "Chèque", "Autre"]
STATUTS = ["emise", "partielle", "payee", "annulee"]
LIBELLE_STATUT = {"emise": "À payer", "partielle": "Partiellement payée", "payee": "Payée", "annulee": "Annulée"}


# ---------- calculs purs (testés) ----------

def repartir(total: int, taux: float) -> tuple[int, int]:
    """(part organisme, part patient) : la part organisme est arrondie à l'entier, la part patient est le complément (aucune dérive)."""
    taux = max(0.0, min(100.0, float(taux or 0)))
    organisme = int(round(total * taux / 100))
    return organisme, total - organisme


def statut_facture(f: dict) -> str:
    """'annulee', 'payee' (tout encaissé), 'partielle' (un début de paiement) ou 'emise'."""
    if f.get("annulee"):
        return "annulee"
    payes = sum(p["montant"] for p in f.get("paiements", []))
    if payes >= f["total"]:
        return "payee"
    return "partielle" if payes > 0 else "emise"


def soldes(f: dict) -> dict:
    """Reste à payer par le patient et par l'organisme (0 pour une facture annulée)."""
    if f.get("annulee"):
        return {"reste_patient": 0, "reste_organisme": 0, "paye_patient": 0, "paye_organisme": 0}
    pp = sum(p["montant"] for p in f.get("paiements", []) if p["payeur"] == "patient")
    po = sum(p["montant"] for p in f.get("paiements", []) if p["payeur"] == "organisme")
    return {"paye_patient": pp, "paye_organisme": po, "reste_patient": f["part_patient"] - pp, "reste_organisme": f["part_organisme"] - po}


def _public(f: dict) -> dict:
    d = {k: v for k, v in f.items() if k != "_id"}
    d["statut"] = statut_facture(f)
    d["statut_libelle"] = LIBELLE_STATUT[d["statut"]]
    d.update(soldes(f))
    d["reste"] = d["reste_patient"] + d["reste_organisme"]
    return d


# ---------- tarifs ----------

@routeur.get("/facturation/listes")
def listes(u: dict = Depends(exiger_roles(roles.FACTURATION))):
    return {"types_organisme": TYPES_ORGANISME, "modes_paiement": MODES_PAIEMENT, "statuts": [{"valeur": s, "libelle": LIBELLE_STATUT[s]} for s in STATUTS]}


@routeur.get("/facturation/tarifs")
def lister_tarifs(u: dict = Depends(exiger_roles(roles.FACTURATION))):
    return list(db.base().tarifs.find({}, {"_id": 0}).sort("libelle", 1))


@routeur.post("/facturation/tarifs")
def creer_tarif(corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Crée un acte facturable (prix en FCFA entier ≥ 0). « automatique » : ajouté à la facture de chaque séance."""
    d = {"libelle": validation.texte(corps, "libelle", "Libellé", True, 100), "prix": _montant(corps, "prix", "Prix", zero_ok=True), "automatique": bool(corps.get("automatique"))}
    if db.base().tarifs.find_one({"libelle": d["libelle"]}):
        raise HTTPException(409, "Un tarif porte déjà ce libellé")
    doc = {"id": str(uuid.uuid4()), **d, "actif": True, "created_at": db.maintenant()}
    db.base().tarifs.insert_one(doc)
    journaliser("tarif_cree", u, d["libelle"])
    return {k: v for k, v in doc.items() if k != "_id"}


@routeur.put("/facturation/tarifs/{tid}")
def modifier_tarif(tid: str, corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Modifie un tarif : les factures déjà émises ne changent pas (prix copiés)."""
    t = db.base().tarifs.find_one({"id": tid})
    if not t:
        raise HTTPException(404, "Tarif introuvable")
    maj: dict = {}
    if "libelle" in corps:
        maj["libelle"] = validation.texte(corps, "libelle", "Libellé", True, 100)
    if "prix" in corps:
        maj["prix"] = _montant(corps, "prix", "Prix", zero_ok=True)
    for k in ("automatique", "actif"):
        if k in corps:
            maj[k] = bool(corps[k])
    if maj:
        db.base().tarifs.update_one({"id": tid}, {"$set": maj})
        journaliser("tarif_modifie", u, f"{t['libelle']} : {', '.join(sorted(maj))}")
    return {k: v for k, v in db.base().tarifs.find_one({"id": tid}).items() if k != "_id"}


# ---------- organismes ----------

@routeur.get("/facturation/organismes")
def lister_organismes(u: dict = Depends(exiger_roles(roles.FACTURATION))):
    return list(db.base().organismes.find({}, {"_id": 0}).sort("nom", 1))


@routeur.post("/facturation/organismes")
def creer_organisme(corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    d = {"nom": validation.texte(corps, "nom", "Nom", True, 100), "type": validation.choix(corps, "type", "Type", TYPES_ORGANISME, obligatoire=True),
         "taux": validation.nombre(corps, "taux", "Taux de prise en charge (%)", 0, 100) or 0, "contact": validation.texte(corps, "contact", "Contact", False, 150)}
    if db.base().organismes.find_one({"nom": d["nom"]}):
        raise HTTPException(409, "Un organisme porte déjà ce nom")
    doc = {"id": str(uuid.uuid4()), **d, "actif": True, "created_at": db.maintenant()}
    db.base().organismes.insert_one(doc)
    journaliser("organisme_cree", u, d["nom"])
    return {k: v for k, v in doc.items() if k != "_id"}


@routeur.put("/facturation/organismes/{oid}")
def modifier_organisme(oid: str, corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    o = db.base().organismes.find_one({"id": oid})
    if not o:
        raise HTTPException(404, "Organisme introuvable")
    maj: dict = {}
    if "nom" in corps:
        maj["nom"] = validation.texte(corps, "nom", "Nom", True, 100)
    if "type" in corps:
        maj["type"] = validation.choix(corps, "type", "Type", TYPES_ORGANISME, obligatoire=True)
    if "taux" in corps:
        maj["taux"] = validation.nombre(corps, "taux", "Taux (%)", 0, 100) or 0
    if "contact" in corps:
        maj["contact"] = validation.texte(corps, "contact", "Contact", False, 150)
    if "actif" in corps:
        maj["actif"] = bool(corps["actif"])
    if maj:
        db.base().organismes.update_one({"id": oid}, {"$set": maj})
        journaliser("organisme_modifie", u, f"{o['nom']} : {', '.join(sorted(maj))}")
    return {k: v for k, v in db.base().organismes.find_one({"id": oid}).items() if k != "_id"}


def _montant(corps: dict, cle: str, libelle: str, zero_ok: bool = False) -> int:
    """Montant FCFA entier (jamais de centimes)."""
    n = validation.nombre(corps, cle, libelle, 0 if zero_ok else 1, 1_000_000_000)
    if n is None or n != int(n):
        validation.erreur(f"{libelle} : montant entier en FCFA obligatoire")
    return int(n)


# ---------- factures ----------

def _numero() -> str:
    from pymongo import ReturnDocument
    an = date.today().year
    n = db.base().parametres.find_one_and_update({"id": f"compteur_factures_{an}"}, {"$inc": {"n": 1}}, upsert=True, return_document=ReturnDocument.AFTER)["n"]
    return f"FAC-{an}-{int(n):06d}"


def _creer_facture(seance: dict, patient: dict, organismes: dict, tarifs_auto: list[dict], u: dict) -> dict:
    """Construit et range la facture d'une séance (copie des prix, noms et taux au moment de l'émission)."""
    lignes = [{"id": str(uuid.uuid4()), "libelle": t["libelle"], "quantite": 1, "prix_unitaire": t["prix"], "total": t["prix"]} for t in tarifs_auto]
    total = sum(l["total"] for l in lignes)
    org = organismes.get(patient.get("organisme_id") or "")
    taux = patient.get("taux_prise_en_charge")
    if taux is None:
        taux = (org or {}).get("taux", 0)
    po, pp = repartir(total, taux if org or patient.get("taux_prise_en_charge") is not None else 0)
    doc = {"id": str(uuid.uuid4()), "numero": _numero(), "date": seance["date"], "seance_id": seance["id"], "patient_id": patient["id"],
           "patient_nom": f"{patient['nom']} {patient['prenom']}", "patient_code": patient["code"],
           "organisme_id": (org or {}).get("id", ""), "organisme_nom": (org or {}).get("nom", ""), "numero_assurance": patient.get("numero_assurance", ""),
           "lignes": lignes, "total": total, "taux": taux if org or patient.get("taux_prise_en_charge") is not None else 0, "part_organisme": po, "part_patient": pp,
           "paiements": [], "annulee": False, "created_at": db.maintenant(), "cree_par": u["login"]}
    db.base().factures.insert_one(doc)
    return doc


@routeur.post("/factures/seance/{sid}")
def facturer_seance(sid: str, u: dict = Depends(exiger_roles(roles.FACTURATION))):
    """Facture UNE séance terminée (une seule facture par séance, sauf si la précédente est annulée)."""
    s = db.base().seances.find_one({"id": sid})
    if not s:
        raise HTTPException(404, "Séance introuvable")
    if s["statut"] != "terminee":
        raise HTTPException(409, "Seule une séance terminée se facture")
    if db.base().factures.find_one({"seance_id": sid, "annulee": False}):
        raise HTTPException(409, "Cette séance est déjà facturée")
    tarifs = list(db.base().tarifs.find({"actif": True, "automatique": True}))
    if not tarifs:
        raise HTTPException(409, "Aucun tarif automatique : créez le tarif de la séance dans « Tarifs »")
    patient = db.base().patients.find_one({"id": s["patient_id"]})
    organismes = {o["id"]: o for o in db.base().organismes.find({})}
    f = _creer_facture(s, patient, organismes, tarifs, u)
    journaliser("facture_creee", u, f["numero"])
    return _public(f)


@routeur.post("/factures/generer")
def generer(corps: dict, u: dict = Depends(exiger_roles(roles.FACTURATION))):
    """Facture toutes les séances TERMINÉES de la période qui n'ont pas de facture (lectures en bloc). Renvoie le nombre créé."""
    du, au = validation.date_iso(corps, "du", "Du", True), validation.date_iso(corps, "au", "Au", True)
    if au < du:
        validation.erreur("Période invalide")
    tarifs = list(db.base().tarifs.find({"actif": True, "automatique": True}))
    if not tarifs:
        raise HTTPException(409, "Aucun tarif automatique : créez le tarif de la séance dans « Tarifs »")
    seances = list(db.base().seances.find({"statut": "terminee", "date": {"$gte": du, "$lte": au}}))
    deja = {f["seance_id"] for f in db.base().factures.find({"seance_id": {"$in": [s["id"] for s in seances]}, "annulee": False}, {"seance_id": 1})} if seances else set()
    patients = {p["id"]: p for p in db.base().patients.find({"id": {"$in": list({s["patient_id"] for s in seances})}})} if seances else {}
    organismes = {o["id"]: o for o in db.base().organismes.find({})}
    crees = 0
    for s in sorted(seances, key=lambda x: (x["date"], x["creneau"])):
        if s["id"] in deja or s["patient_id"] not in patients:
            continue
        _creer_facture(s, patients[s["patient_id"]], organismes, tarifs, u)
        crees += 1
    journaliser("factures_generees", u, f"{du} → {au} : {crees}")
    return {"creees": crees, "deja_facturees": len(deja)}


@routeur.get("/factures")
def lister(statut: str = "", patient_id: str = "", organisme_id: str = "", du: str = "", au: str = "", u: dict = Depends(exiger_roles(roles.FACTURATION))):
    """Factures filtrées (500 au plus, les plus récentes d'abord) avec statut et soldes."""
    f: dict = {}
    for cle, v in (("patient_id", patient_id), ("organisme_id", organisme_id)):
        if v:
            f[cle] = v
    if du or au:
        f["date"] = {}
        if du:
            f["date"]["$gte"] = validation.date_iso({"d": du}, "d", "Du")
        if au:
            f["date"]["$lte"] = validation.date_iso({"d": au}, "d", "Au")
    res = [_public(x) for x in db.base().factures.find(f).sort([("date", -1), ("numero", -1)]).limit(500)]
    return [x for x in res if not statut or x["statut"] == statut]


def _facture(fid: str) -> dict:
    f = db.base().factures.find_one({"id": fid})
    if not f:
        raise HTTPException(404, "Facture introuvable")
    return f


@routeur.get("/factures/{fid}")
def lire(fid: str, u: dict = Depends(exiger_roles(roles.FACTURATION))):
    return _public(_facture(fid))


@routeur.post("/factures/{fid}/paiements")
def payer(fid: str, corps: dict, u: dict = Depends(exiger_roles(roles.FACTURATION))):
    """Enregistre un paiement du patient ou de l'organisme : jamais au-delà du reste dû par ce payeur ; jamais sur une facture annulée."""
    f = _facture(fid)
    if f.get("annulee"):
        raise HTTPException(409, "Facture annulée")
    payeur = validation.choix(corps, "payeur", "Payeur", ["patient", "organisme"], obligatoire=True)
    if payeur == "organisme" and not f["organisme_id"]:
        raise HTTPException(409, "Cette facture n'a pas d'organisme payeur")
    montant = _montant(corps, "montant", "Montant")
    reste = soldes(f)["reste_" + payeur]
    if montant > reste:
        raise HTTPException(409, f"Montant supérieur au reste dû par ce payeur ({reste} FCFA)")
    p = {"id": str(uuid.uuid4()), "payeur": payeur, "montant": montant, "mode": validation.choix(corps, "mode", "Mode de paiement", MODES_PAIEMENT, obligatoire=True),
         "reference": validation.texte(corps, "reference", "Référence", False, 80), "date": validation.date_iso(corps, "date", "Date", False, futur_ok=False) or db.maintenant()[:10],
         "par": u["login"], "created_at": db.maintenant()}
    db.base().factures.update_one({"id": fid}, {"$push": {"paiements": p}})
    journaliser("paiement_enregistre", u, f"{f['numero']} {payeur} {montant}")
    return _public(_facture(fid))


@routeur.post("/factures/{fid}/annuler")
def annuler(fid: str, corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Annule une facture (administration, motif obligatoire, aucun paiement enregistré) : la séance peut alors être refacturée."""
    f = _facture(fid)
    if f.get("annulee"):
        raise HTTPException(409, "Facture déjà annulée")
    if f.get("paiements"):
        raise HTTPException(409, "Des paiements sont enregistrés : une facture payée ne s'annule pas")
    motif = validation.texte(corps, "motif", "Motif", True, 200)
    db.base().factures.update_one({"id": fid}, {"$set": {"annulee": True, "motif_annulation": motif, "annulee_par": u["login"], "annulee_le": db.maintenant()}})
    journaliser("facture_annulee", u, f["numero"])
    return _public(_facture(fid))


@routeur.get("/facturation/synthese")
def synthese(du: str, au: str, u: dict = Depends(exiger_roles(roles.FACTURATION))):
    """
    Synthèse d'une période (factures non annulées, lues EN BLOC) : facturé, encaissé (patients / organismes), reste à encaisser,
    créances par organisme et patients ayant un reste à payer.
    """
    du, au = validation.date_iso({"d": du}, "d", "Du", True), validation.date_iso({"d": au}, "d", "Au", True)
    fs = [_public(f) for f in db.base().factures.find({"date": {"$gte": du, "$lte": au}, "annulee": False})]
    par_org: dict = {}
    par_patient: dict = {}
    for f in fs:
        if f["organisme_id"] and f["reste_organisme"] > 0:
            o = par_org.setdefault(f["organisme_id"], {"organisme": f["organisme_nom"], "factures": 0, "reste": 0})
            o["factures"] += 1
            o["reste"] += f["reste_organisme"]
        if f["reste_patient"] > 0:
            p = par_patient.setdefault(f["patient_id"], {"patient": f["patient_nom"], "code": f["patient_code"], "factures": 0, "reste": 0})
            p["factures"] += 1
            p["reste"] += f["reste_patient"]
    return {"du": du, "au": au, "nombre": len(fs), "facture": sum(f["total"] for f in fs), "encaisse_patients": sum(f["paye_patient"] for f in fs),
            "encaisse_organismes": sum(f["paye_organisme"] for f in fs), "reste": sum(f["reste"] for f in fs),
            "creances_organismes": sorted(par_org.values(), key=lambda x: -x["reste"]), "impayes_patients": sorted(par_patient.values(), key=lambda x: -x["reste"])}


# ---------- paramètres d'en-tête et PDF ----------

@routeur.get("/facturation/clinique")
def lire_clinique(u: dict = Depends(exiger_roles(roles.FACTURATION))):
    return {k: v for k, v in (db.base().parametres.find_one({"id": "clinique"}) or {}).items() if k not in ("_id", "id")}


@routeur.put("/facturation/clinique")
def ecrire_clinique(corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """En-tête des factures : nom, adresse, téléphone, n° IFU / RCCM."""
    d = {k: validation.texte(corps, k, lib, False, 150) for k, lib in (("nom", "Nom"), ("adresse", "Adresse"), ("telephone", "Téléphone"), ("identifiant_fiscal", "IFU / RCCM"))}
    db.base().parametres.update_one({"id": "clinique"}, {"$set": d}, upsert=True)
    journaliser("clinique_modifiee", u)
    return d


def fcfa(n: int) -> str:
    """12345 → « 12 345 FCFA » (espace insécable fine remplacée par une espace simple pour le PDF)."""
    return f"{int(n):,}".replace(",", " ") + " FCFA"


def pdf_facture(f: dict, clinique: dict) -> bytes:
    """PDF d'une facture (reportlab) : en-tête, patient, lignes, répartition, paiements. Montants alignés à DROITE (règle des tableaux)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=f["numero"])
    st = getSampleStyleSheet()
    droite = ParagraphStyle("droite", parent=st["Normal"], alignment=2)
    titre = ParagraphStyle("titre", parent=st["Title"], textColor=colors.HexColor("#0A1E3D"), alignment=0)
    p = f["paiements"]
    from .centres import element_logo
    logo = element_logo(clinique)
    elements = ([logo, Spacer(1, 2 * mm)] if logo else []) + [Paragraph(clinique.get("nom") or "Clinique de dialyse", titre),
                Paragraph(" · ".join(x for x in (clinique.get("adresse"), clinique.get("telephone"), clinique.get("identifiant_fiscal")) if x), st["Normal"]),
                *([Paragraph(f"{clinique.get('titre_responsable') or 'Responsable'} : {clinique['responsable']}", st["Normal"])] if clinique.get("responsable") else []), Spacer(1, 6 * mm),
                Paragraph(f"<b>FACTURE {f['numero']}</b> — séance du {f['date'][8:]}/{f['date'][5:7]}/{f['date'][:4]}" + (" — <font color='red'>ANNULÉE</font>" if f.get("annulee") else ""), st["Heading3"]),
                Paragraph(f"Patient : <b>{f['patient_nom']}</b> ({f['patient_code']})", st["Normal"])]
    if f["organisme_nom"]:
        elements.append(Paragraph(f"Organisme payeur : {f['organisme_nom']} — prise en charge {f['taux']:g} %" + (f" — n° {f['numero_assurance']}" if f.get("numero_assurance") else ""), st["Normal"]))
    elements.append(Spacer(1, 5 * mm))
    lignes = [["Désignation", "Qté", "Prix unitaire", "Total"]] + [[l["libelle"], str(l["quantite"]), fcfa(l["prix_unitaire"]), fcfa(l["total"])] for l in f["lignes"]]
    t = Table(lignes, colWidths=[85 * mm, 15 * mm, 35 * mm, 35 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                           ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    elements += [t, Spacer(1, 4 * mm)]
    s = soldes(f)
    recap = [["Total", fcfa(f["total"])], ["Part de l'organisme", fcfa(f["part_organisme"])], ["Part du patient", fcfa(f["part_patient"])],
             ["Déjà payé", fcfa(s["paye_patient"] + s["paye_organisme"])], ["Reste à payer", fcfa(s["reste_patient"] + s["reste_organisme"])]]
    r = Table(recap, colWidths=[135 * mm, 35 * mm], hAlign="RIGHT")
    r.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.black)]))
    elements.append(r)
    if p:
        elements += [Spacer(1, 6 * mm), Paragraph("<b>Paiements</b>", st["Normal"])]
        pt = Table([["Date", "Payeur", "Mode", "Montant"]] + [[x["date"], "Patient" if x["payeur"] == "patient" else "Organisme", x["mode"], fcfa(x["montant"])] for x in p], colWidths=[30 * mm, 40 * mm, 60 * mm, 40 * mm])
        pt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")), ("ALIGN", (3, 0), (3, -1), "RIGHT"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9"))]))
        elements.append(pt)
    doc.build(elements)
    return tampon.getvalue()


@routeur.get("/factures/{fid}/pdf")
def pdf(fid: str, u: dict = Depends(exiger_roles(roles.FACTURATION))):
    """PDF de la facture servi en « inline » (affiché dans le lecteur de l'application, jamais téléchargé)."""
    f = _facture(fid)
    from .centres import entete_courant
    clinique = entete_courant()                        # fiche du centre (logo, responsable…), complétée par l'ancien en-tête des factures
    journaliser("facture_pdf", u, f["numero"])
    return Response(pdf_facture(f, clinique), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{f["numero"]}.pdf"'})
