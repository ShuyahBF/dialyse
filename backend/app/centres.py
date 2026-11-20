"""
Centres de dialyse (multi-centres, sur le modèle d'e-Kol : « une école = un centre »).

Chaque centre possède SES patients, postes, séances, bilans, stocks, factures, modèles de dossier et SES utilisateurs. Le compte d'un centre ne voit
jamais un autre centre (le serveur filtre, voir `db.CollectionCentree`). Le super administrateur crée les centres ; lui et le directeur général (comptes
« du groupe », sans centre) choisissent le centre où ils travaillent.
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException

from . import db, roles, validation
from .auth import exiger_roles, journaliser, utilisateur_courant

routeur = APIRouter()

CENTRE_INITIAL = "centre-initial"          # identifiant du centre créé automatiquement pour reprendre les données d'avant le multi-centres
PREFIXE_INITIAL = "DIAL"                   # préfixe des codes patients existants (DIAL-000001) : conservé pour le centre initial


# Champs de présentation du centre (en-tête des papiers) : texte libre, longueur maximale.
CHAMPS_TEXTE = (("responsable", "Nom du responsable", 100), ("titre_responsable", "Fonction du responsable", 80), ("adresse", "Adresse", 150),
                ("ville", "Ville", 80), ("telephone", "Téléphone", 30), ("email", "E-mail", 100), ("identifiant_fiscal", "IFU / RCCM", 80))
LOGO_MAX_OCTETS = 600_000          # image reçue : 600 Ko au plus (elle est ensuite réduite à 480 px et ré-encodée en PNG)
LOGO_COTE_MAX = 480


def _public(c: dict, avec_logo: bool = False) -> dict:
    """Fiche d'un centre telle qu'elle est montrée à l'écran. Le logo (lourd) n'est joint que sur demande, jamais dans les listes."""
    d = {"id": c["id"], "nom": c["nom"], "prefixe": c["prefixe"], "actif": c.get("actif", True), "cree_le": c.get("cree_le", ""),
         "latitude": c.get("latitude"), "longitude": c.get("longitude"), "a_logo": bool(c.get("logo"))}
    for cle, _lib, _max in CHAMPS_TEXTE:
        d[cle] = c.get(cle, "")
    # Ligne WhatsApp dédiée du centre : émetteur SAWALI propre, variable de clé à saisir dans Render (jamais la clé elle-même), repli facultatif sur la ligne partagée
    from . import whatsapp
    d["wa_emetteur"] = c.get("wa_emetteur", "")
    d["wa_repli"] = bool(c.get("wa_repli"))
    d["wa_variable"] = whatsapp.variable_cle_centre(c.get("prefixe", ""))
    d["wa_cle_presente"] = bool(c.get("wa_emetteur")) and bool(whatsapp.ligne_du_centre(c.get("id")))
    if avec_logo:
        d["logo"] = ("data:image/png;base64," + c["logo"]) if c.get("logo") else ""
    return d


def _champs_presentation(corps: dict) -> dict:
    """Champs de présentation validés (seulement ceux présents) : textes, géolocalisation (latitude et longitude ensemble, ou toutes deux vides)."""
    maj: dict = {}
    for cle, libelle, long_ in CHAMPS_TEXTE:
        if cle in corps:
            maj[cle] = validation.texte(corps, cle, libelle, False, long_)
    if "wa_emetteur" in corps:
        code = str(corps.get("wa_emetteur") or "").strip().lower()
        if code and not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,38}[a-z0-9]", code):
            validation.erreur("Émetteur WhatsApp : 3 à 40 caractères (lettres minuscules, chiffres, tiret), comme créé dans SAWALI")
        maj["wa_emetteur"] = code
    if "wa_repli" in corps:
        maj["wa_repli"] = bool(corps["wa_repli"])
    if "latitude" in corps or "longitude" in corps:
        brut = (corps.get("latitude"), corps.get("longitude"))
        if all(v in (None, "") for v in brut):
            maj["latitude"] = maj["longitude"] = None
        else:
            try:
                lat, lon = float(brut[0]), float(brut[1])
            except (TypeError, ValueError):
                validation.erreur("Géolocalisation : latitude et longitude doivent être des nombres")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                validation.erreur("Géolocalisation : latitude entre -90 et 90, longitude entre -180 et 180")
            maj["latitude"], maj["longitude"] = round(lat, 6), round(lon, 6)
    return maj


def _logo_depuis_corps(corps: dict) -> str | None:
    """
    Logo reçu en « data URL » (base64). Vérifié RÉELLEMENT avec Pillow (format PNG, JPEG ou WebP ; jamais cru sur l'extension), réduit à 480 px au plus et ré-encodé en
    PNG (métadonnées retirées). Retourne le PNG en base64, ou "" pour retirer le logo.
    """
    import base64
    import io
    brut = str(corps.get("logo") or "")
    if not brut:
        return ""
    try:
        donnees = base64.b64decode(brut.split(",", 1)[-1], validate=False)
    except Exception:
        validation.erreur("Logo illisible")
    if len(donnees) > LOGO_MAX_OCTETS:
        validation.erreur("Logo trop lourd : 600 Ko au plus")
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(donnees))
        if img.format not in ("PNG", "JPEG", "WEBP"):
            raise ValueError
        img = img.convert("RGBA")
        img.thumbnail((LOGO_COTE_MAX, LOGO_COTE_MAX))
        sortie = io.BytesIO()
        img.save(sortie, "PNG", optimize=True)
    except Exception:
        validation.erreur("Logo : image PNG, JPEG ou WebP attendue")
    return base64.b64encode(sortie.getvalue()).decode()


def amorcer_centre_initial() -> None:
    """
    Migration idempotente vers le multi-centres : s'il n'existe aucun centre, crée « Centre principal » et y rattache TOUTES les données
    existantes (patients, séances… et comptes, sauf les comptes du groupe). Relancée à chaque démarrage sans effet une fois faite.
    """
    b = db.brut()
    orphelins = any(b[n].count_documents({"centre_id": {"$exists": False}}, limit=1) for n in db.COLLECTIONS_CENTRE | {"journal"}) \
        or b.utilisateurs.count_documents({"centre_id": {"$exists": False}, "role": {"$nin": list(roles.ROLES_GROUPE)}}, limit=1)
    if not b.centres.find_one({"id": CENTRE_INITIAL}) and (b.centres.count_documents({}) == 0 or orphelins):
        b.centres.insert_one({"id": CENTRE_INITIAL, "nom": "Centre principal", "prefixe": PREFIXE_INITIAL, "ville": "", "telephone": "",
                              "actif": True, "cree_le": db.maintenant()})
    ancien = b.centres.find_one({"id": CENTRE_INITIAL})
    if not ancien:
        return                                                  # centres déjà créés à la main : rien à rattacher d'office
    for nom in db.COLLECTIONS_CENTRE | {"journal"}:
        b[nom].update_many({"centre_id": {"$exists": False}}, {"$set": {"centre_id": CENTRE_INITIAL}})
    b.utilisateurs.update_many({"centre_id": {"$exists": False}, "role": {"$nin": list(roles.ROLES_GROUPE)}}, {"$set": {"centre_id": CENTRE_INITIAL}})
    b.utilisateurs.update_many({"centre_id": {"$exists": False}}, {"$set": {"centre_id": None}})
    b.jetons_alertes.update_many({"centre_id": {"$exists": False}}, {"$set": {"centre_id": CENTRE_INITIAL}})


def _prefixe(corps: dict, id_actuel: str = "") -> str:
    """Préfixe des codes patients du centre (2 à 6 lettres ou chiffres, majuscules), unique."""
    p = validation.texte(corps, "prefixe", "Préfixe des codes patients", True, 6).upper()
    if not re.fullmatch(r"[A-Z0-9]{2,6}", p):
        validation.erreur("Préfixe : 2 à 6 lettres ou chiffres (exemple : CMC)")
    autre = db.brut().centres.find_one({"prefixe": p, "id": {"$ne": id_actuel}})
    if autre:
        raise HTTPException(409, "Ce préfixe est déjà utilisé par un autre centre")
    return p


@routeur.get("/centres")
def lister(u: dict = Depends(utilisateur_courant)):
    """Centres visibles : tous pour un compte du groupe (liste du sélecteur), le sien seulement pour les autres."""
    if u["role"] in roles.ROLES_GROUPE and u["groupe"]:
        lignes = db.brut().centres.find({}, {"_id": 0}).sort("nom", 1)
    else:
        lignes = db.brut().centres.find({"id": u["centre_id"]}, {"_id": 0})
    return [_public(c) for c in lignes]


@routeur.post("/centres")
def creer(corps: dict, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Crée un centre (super administrateur seulement)."""
    nom = validation.texte(corps, "nom", "Nom du centre", True, 80)
    doc = {"id": str(uuid.uuid4()), "nom": nom, "prefixe": _prefixe(corps), "actif": True, "cree_le": db.maintenant(), **_champs_presentation(corps)}
    if corps.get("logo"):
        doc["logo"] = _logo_depuis_corps(corps)
    db.brut().centres.insert_one(doc)
    journaliser("centre_cree", u, f"{nom} ({doc['prefixe']})")
    return _public(doc)


@routeur.put("/centres/{id_}")
def modifier(id_: str, corps: dict, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Modifie le nom, la ville, le téléphone ou l'état (actif / désactivé) d'un centre. Le préfixe ne change plus une fois des patients créés."""
    c = db.brut().centres.find_one({"id": id_})
    if not c:
        raise HTTPException(404, "Centre introuvable")
    maj: dict = _champs_presentation(corps)
    if "nom" in corps:
        maj["nom"] = validation.texte(corps, "nom", "Nom du centre", True, 80)
    if "logo" in corps:
        maj["logo"] = _logo_depuis_corps(corps)
    if "prefixe" in corps and str(corps["prefixe"]).upper() != c["prefixe"]:
        if db.brut().patients.count_documents({"centre_id": id_}):
            raise HTTPException(409, "Le préfixe ne peut plus changer : des patients portent déjà ce préfixe")
        maj["prefixe"] = _prefixe(corps, id_)
    if "actif" in corps:
        maj["actif"] = bool(corps["actif"])
    if maj:
        db.brut().centres.update_one({"id": id_}, {"$set": maj})
        journaliser("centre_modifie", u, f"{c['nom']} : {', '.join(sorted(maj))}")
    return _public(db.brut().centres.find_one({"id": id_}), avec_logo=True)


@routeur.get("/centres/{id_}")
def lire(id_: str, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Fiche complète d'un centre, logo compris (écran de modification du super administrateur)."""
    c = db.brut().centres.find_one({"id": id_})
    if not c:
        raise HTTPException(404, "Centre introuvable")
    return _public(c, avec_logo=True)


# ---------- le centre de travail : fiche, papier à en-tête ----------

@routeur.get("/centre")
def centre_courant_fiche(u: dict = Depends(exiger_roles(roles.LECTURE_PATIENT | roles.FACTURATION | roles.ADMINISTRATION | {roles.DIRECTION, roles.TECHNICIEN}))):
    """Fiche du centre de travail (logo compris) : pour l'en-tête de l'écran et la modification par l'administrateur du centre."""
    return _public(db.brut().centres.find_one({"id": u["centre_id"]}) or {"id": "", "nom": "", "prefixe": ""}, avec_logo=True) if u["centre_id"] else {}


@routeur.put("/centre")
def modifier_mon_centre(corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """
    L'administrateur du centre (ou le super administrateur ayant choisi un centre) tient la FICHE de présentation : responsable, adresse, téléphone, e-mail, IFU / RCCM,
    géolocalisation, logo. Le nom, le préfixe et l'état du centre restent au super administrateur.
    """
    if not u["centre_id"]:
        raise HTTPException(400, "Choisissez d'abord un centre de dialyse")
    maj = _champs_presentation(corps)
    if u["role"] != roles.SUPER_ADMIN:                           # la ligne WhatsApp dédiée se règle au niveau du groupe (super administrateur), pas par l'administrateur du centre
        maj.pop("wa_emetteur", None)
        maj.pop("wa_repli", None)
    if "logo" in corps:
        maj["logo"] = _logo_depuis_corps(corps)
    if maj:
        db.brut().centres.update_one({"id": u["centre_id"]}, {"$set": maj})
        journaliser("centre_fiche_modifiee", u, ", ".join(sorted(maj)))
    return _public(db.brut().centres.find_one({"id": u["centre_id"]}), avec_logo=True)


def entete_courant() -> dict:
    """
    En-tête des papiers du centre de travail : la fiche du centre, complétée (et au besoin remplacée) par les anciens réglages « en-tête des factures »
    quand ils sont renseignés. Contient `logo_png` (octets) si le centre a un logo.
    """
    import base64
    c = db.brut().centres.find_one({"id": db.centre_courant.get()}) or {}
    ancien = db.base().parametres.find_one({"id": "clinique"}) or {}
    e = {k: c.get(k, "") for k, _l, _m in CHAMPS_TEXTE}
    e["nom"] = ancien.get("nom") or c.get("nom", "")
    for cle in ("adresse", "telephone", "identifiant_fiscal"):
        e[cle] = ancien.get(cle) or e.get(cle, "")
    e["latitude"], e["longitude"] = c.get("latitude"), c.get("longitude")
    e["logo_png"] = base64.b64decode(c["logo"]) if c.get("logo") else None
    return e


def element_logo(entete: dict, hauteur_mm: float = 18):
    """Logo (flowable reportlab) à hauteur fixe, proportions respectées ; None sans logo."""
    if not entete.get("logo_png"):
        return None
    import io
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    l, h = ImageReader(io.BytesIO(entete["logo_png"])).getSize()
    img = Image(io.BytesIO(entete["logo_png"]), width=hauteur_mm * mm * l / h, height=hauteur_mm * mm)
    img.hAlign = "LEFT"
    return img


def pdf_papier_entete(e: dict, format_: str) -> bytes:
    """
    Papier à en-tête du centre, VIERGE (à imprimer ou à enregistrer comme modèle de lettre) : en haut logo, nom du centre, responsable et coordonnées ; en bas
    rappel des coordonnées et position GPS. Formats A4 (210 × 297 mm) et A5 (148 × 210 mm) : les marges et les tailles de texte suivent le format.
    """
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, A5
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    largeur, hauteur = A4 if format_ == "A4" else A5
    k = 1.0 if format_ == "A4" else 0.78                      # facteur d'échelle des tailles
    marge = 18 * mm * k
    tampon = io.BytesIO()
    p = canvas.Canvas(tampon, pagesize=(largeur, hauteur), pageCompression=1)
    p.setTitle(f"Papier à en-tête {format_} — {e.get('nom', '')}")
    y = hauteur - 14 * mm * k
    x_texte = marge
    if e.get("logo_png"):
        lg, hg = ImageReader(io.BytesIO(e["logo_png"])).getSize()
        h_logo = 20 * mm * k
        l_logo = h_logo * lg / hg
        p.drawImage(ImageReader(io.BytesIO(e["logo_png"])), marge, y - h_logo, width=l_logo, height=h_logo, mask="auto")
        x_texte = marge + l_logo + 6 * mm * k
    p.setFillColor(colors.HexColor("#0A1E3D"))
    p.setFont("Helvetica-Bold", 15 * k)
    p.drawString(x_texte, y - 7 * mm * k, (e.get("nom") or "Centre de dialyse")[:60])
    p.setFont("Helvetica", 9 * k)
    p.setFillColor(colors.HexColor("#56627A"))
    lignes = []
    if e.get("responsable"):
        lignes.append(f"{e.get('titre_responsable') or 'Responsable'} : {e['responsable']}")
    adr = " · ".join(x for x in (e.get("adresse"), e.get("ville")) if x)
    if adr:
        lignes.append(adr)
    contact = " · ".join(x for x in (("Tél. " + e["telephone"]) if e.get("telephone") else "", e.get("email")) if x)
    if contact:
        lignes.append(contact)
    for i, t in enumerate(lignes):
        p.drawString(x_texte, y - (12.5 + 4.6 * i) * mm * k, t[:95])
    # filet de séparation orange (couleur d'accent de la plateforme)
    yf = y - 26 * mm * k
    p.setStrokeColor(colors.HexColor("#FF7A0A"))
    p.setLineWidth(1.4)
    p.line(marge, yf, largeur - marge, yf)
    # pied de page : identifiant fiscal, adresse et position GPS
    p.setStrokeColor(colors.HexColor("#CBD5E1"))
    p.setLineWidth(0.5)
    p.line(marge, 16 * mm * k, largeur - marge, 16 * mm * k)
    p.setFont("Helvetica", 7.5 * k)
    p.setFillColor(colors.HexColor("#56627A"))
    pied = [x for x in (e.get("identifiant_fiscal") and "IFU / RCCM : " + e["identifiant_fiscal"], adr) if x]
    if pied:
        p.drawCentredString(largeur / 2, 11.5 * mm * k, " — ".join(pied)[:140])
    if e.get("latitude") is not None and e.get("longitude") is not None:
        p.drawCentredString(largeur / 2, 7.5 * mm * k, f"Position GPS : {e['latitude']:.6f}, {e['longitude']:.6f}")
    p.showPage()
    p.save()
    return tampon.getvalue()


@routeur.get("/centre/papier-entete")
def papier_entete(format: str = "A4", u: dict = Depends(exiger_roles(roles.FACTURATION | {roles.DIRECTION}))):
    """Papier à en-tête vierge du centre de travail, en A4 ou A5, servi « inline » (lecteur interne de l'application)."""
    from fastapi.responses import Response
    f = format.upper()
    if f not in ("A4", "A5"):
        validation.erreur("Format : A4 ou A5")
    journaliser("papier_entete", u, f)
    return Response(pdf_papier_entete(entete_courant(), f), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="papier-entete-{f}.pdf"'})
