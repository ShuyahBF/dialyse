"""
PRÉVISIONS DE STOCK ET BON DE COMMANDE (lot 28) : quand chaque consommable va-t-il manquer, et que faut-il commander pour tenir la période choisie ?

Calcul PAR ARTICLE (lectures en bloc, règle 7 : une requête par collection) :
  - conso_jour       = sorties + pertes des `fenetre` derniers jours / `fenetre` ;
  - besoin           = articles « par séance » : séances PLANIFIÉES des `couverture` prochains jours x quantité par séance (ce qui est réellement prévu) ;
                       les autres, ou sans séance prévue : conso_jour x `couverture` ;
  - stock utilisable = lots NON périmés (un lot périmé ne soigne personne) ;
  - jours restants   = stock utilisable / consommation journalière prévue ; rupture estimée = aujourd'hui + jours restants ;
  - à commander      = besoin + seuil d'alerte (stock de sécurité) − stock utilisable, arrondi à l'unité supérieure, jamais négatif ;
  - statut           = rupture (rien d'utilisable) · urgent (moins de 7 jours) · à commander · ok.
Prix : celui du dernier lot reçu AVEC prix ; le coût estimé n'est vu que de l'administration (comme les autres prix, lot 27) ; un article sans prix connu est signalé, jamais deviné.
Le bon de commande (PDF sur le papier à en-tête du centre) liste ce qui est en rupture, urgent ou à commander. Une prévision AIDE à commander, elle ne commande rien toute seule.

Pour un développeur WinDev : c'est une requête de synthèse (comme un état « articles à réapprovisionner ») avec une colonne calculée par article.
"""
from __future__ import annotations

import io
import math
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from . import db, roles, validation
from .auth import exiger_roles, journaliser
from .stock import statut_peremption

routeur = APIRouter()

COUVERTURES = [15, 30, 60, 90]            # jours à couvrir proposés à l'écran (liste déroulante)
FENETRE_JOURS = 30                        # période d'observation de la consommation passée
JOURS_URGENT = 7
ORDRE_STATUT = {"rupture": 0, "urgent": 1, "a_commander": 2, "ok": 3}
LIBELLE_STATUT = {"rupture": "Rupture", "urgent": "Urgent", "a_commander": "À commander", "ok": "Suffisant"}


def _arrondi_haut(x: float) -> int:
    """Quantité entière à commander (on arrondit toujours vers le haut ; les erreurs d'arrondi flottant sont écartées)."""
    return int(math.ceil(round(x, 4)))


def calculer(couverture: int = 30, fenetre: int = FENETRE_JOURS, aujourd_hui: date | None = None) -> dict:
    """Prévisions du centre de travail. Les prix sont inclus ici ; la route les retire pour les comptes qui n'ont pas le droit de les voir."""
    auj = aujourd_hui or date.today()
    iso = auj.isoformat()
    base = db.base()
    articles = list(base.articles.find({"actif": True}, {"_id": 0}).sort("nom", 1))
    lots = list(base.lots.find({}, {"_id": 0, "article_id": 1, "quantite_restante": 1, "peremption": 1, "cout_unitaire": 1, "recu_le": 1}))
    debut = (auj - timedelta(days=fenetre)).isoformat()
    consomme: dict = {}
    for m in base.mouvements.find({"type": {"$in": ["sortie", "perte"]}, "date": {"$gte": debut, "$lte": iso}}, {"_id": 0, "article_id": 1, "delta": 1}):
        consomme[m["article_id"]] = consomme.get(m["article_id"], 0.0) - float(m.get("delta") or 0)
    fin = (auj + timedelta(days=couverture)).isoformat()
    seances = base.seances.count_documents({"date": {"$gte": iso, "$lte": fin}, "statut": {"$in": ["planifiee", "en_cours"]}})
    utilisable: dict = {}
    dernier_prix: dict = {}           # article → (date de réception, prix) du lot le plus récent AVEC prix
    for l in lots:
        if (l.get("quantite_restante") or 0) > 0 and statut_peremption(l.get("peremption", ""), auj) != "perime":
            utilisable[l["article_id"]] = utilisable.get(l["article_id"], 0.0) + float(l["quantite_restante"])
        if l.get("cout_unitaire") is not None and (l["article_id"] not in dernier_prix or (l.get("recu_le") or "") >= dernier_prix[l["article_id"]][0]):
            dernier_prix[l["article_id"]] = (l.get("recu_le") or "", int(l["cout_unitaire"]))
    lignes = []
    for a in articles:
        stock = round(utilisable.get(a["id"], 0.0), 4)
        par_seance = float(a.get("par_seance") or 0)
        conso_jour = consomme.get(a["id"], 0.0) / fenetre
        if par_seance > 0 and seances > 0:
            besoin, par_jour = par_seance * seances, par_seance * seances / couverture
        else:
            besoin, par_jour = conso_jour * couverture, conso_jour
        jours = (stock / par_jour) if par_jour > 0 else None
        seuil = float(a.get("seuil_alerte") or 0)
        a_commander = max(0, _arrondi_haut(besoin + seuil - stock))
        if stock <= 0 and (besoin > 0 or seuil > 0):
            statut = "rupture"
        elif jours is not None and jours < JOURS_URGENT:
            statut = "urgent"
        elif a_commander > 0:
            statut = "a_commander"
        else:
            statut = "ok"
        prix = dernier_prix.get(a["id"], (None, None))[1]
        lignes.append({"article_id": a["id"], "code": a.get("code", ""), "nom": a["nom"], "categorie": a.get("categorie", ""), "unite": a.get("unite", ""),
                       "stock": stock, "stock_perime": round(float(a.get("stock") or 0) - stock, 4) if (a.get("stock") or 0) > stock else 0,
                       "conso_jour": round(par_jour, 3), "besoin": round(besoin, 2), "jours_restants": None if jours is None else round(jours, 1),
                       "rupture_estimee": None if jours is None else (auj + timedelta(days=int(jours))).isoformat(),
                       "seuil": seuil, "a_commander": a_commander, "statut": statut, "statut_libelle": LIBELLE_STATUT[statut],
                       "prix_unitaire": prix, "cout_estime": None if prix is None else a_commander * prix})
    lignes.sort(key=lambda x: (ORDRE_STATUT[x["statut"]], x["nom"].lower()))
    a_cmd = [l for l in lignes if l["statut"] != "ok" and l["a_commander"] > 0]
    totaux = {"articles": len(lignes), "a_commander": len(a_cmd), "en_rupture": sum(1 for l in lignes if l["statut"] == "rupture"),
              "urgents": sum(1 for l in lignes if l["statut"] == "urgent"), "cout_estime": sum(l["cout_estime"] or 0 for l in a_cmd),
              "sans_prix": sum(1 for l in a_cmd if l["prix_unitaire"] is None)}
    return {"date": iso, "couverture": couverture, "fenetre": fenetre, "seances_prevues": seances, "lignes": lignes, "totaux": totaux}


def _sans_prix(res: dict) -> dict:
    """Retire prix et coûts (vus de l'administration seule)."""
    return {**res, "lignes": [{k: v for k, v in l.items() if k not in ("prix_unitaire", "cout_estime")} for l in res["lignes"]],
            "totaux": {k: v for k, v in res["totaux"].items() if k not in ("cout_estime", "sans_prix")}}


def _voit_les_prix(u: dict) -> bool:
    return u["role"] in (roles.ADMIN, roles.SUPER_ADMIN)


def _couverture(valeur: int) -> int:
    if valeur not in COUVERTURES:
        validation.erreur(f"Couverture : {', '.join(str(c) for c in COUVERTURES)} jours")
    return valeur


@routeur.get("/stock/previsions")
def previsions(couverture: int = 30, u: dict = Depends(exiger_roles(roles.LECTURE_STOCK))):
    """Prévisions de rupture et quantités à commander pour tenir `couverture` jours (15, 30, 60 ou 90). Prix et coûts : administration seule."""
    res = calculer(_couverture(couverture))
    return {**(res if _voit_les_prix(u) else _sans_prix(res)), "couvertures": COUVERTURES, "prix_visibles": _voit_les_prix(u)}


def pdf_bon_de_commande(res: dict, entete: dict, avec_prix: bool, etabli_par: str) -> bytes:
    """Bon de commande A4 sur le papier à en-tête du centre : une ligne par article à commander ; prix et total seulement si `avec_prix` (administration)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from .centres import element_logo
    lignes = [l for l in res["lignes"] if l["statut"] != "ok" and l["a_commander"] > 0]
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=16 * mm, title=f"Bon de commande — {entete.get('nom', '')}")
    st = getSampleStyleSheet()
    titre = ParagraphStyle("t", parent=st["Title"], fontSize=15, textColor=colors.HexColor("#0A1E3D"), alignment=0, spaceAfter=2)
    petit = ParagraphStyle("p", parent=st["Normal"], fontSize=8.5, textColor=colors.HexColor("#56627A"))
    normal = ParagraphStyle("n", parent=st["Normal"], fontSize=8.5, leading=10)
    droite = ParagraphStyle("d", parent=normal, alignment=2)                         # nombres alignés à DROITE (règle 3)
    droite_gras = ParagraphStyle("dg", parent=droite, fontName="Helvetica-Bold")
    elements = []
    logo = element_logo(entete, 16)
    if logo:
        elements.append(logo)
    elements.append(Paragraph(entete.get("nom") or "Centre de dialyse", titre))
    coord = " · ".join(x for x in (entete.get("adresse"), entete.get("ville"), ("Tél. " + entete["telephone"]) if entete.get("telephone") else "") if x)
    if coord:
        elements.append(Paragraph(coord, petit))
    elements += [Spacer(1, 5 * mm), Paragraph(f"<b>BON DE COMMANDE — consommables</b> · établi le {res['date'][8:]}/{res['date'][5:7]}/{res['date'][:4]} par {etabli_par}", normal),
                 Paragraph(f"Quantités pour couvrir {res['couverture']} jours ({res['seances_prevues']} séance(s) planifiée(s)), stock de sécurité compris.", petit), Spacer(1, 4 * mm)]
    entetes = ["Code", "Article", "Unité", "Stock utilisable", "À commander"] + (["Prix unitaire", "Montant estimé"] if avec_prix else [])
    donnees = [[Paragraph(f"<b>{h}</b>", droite if i >= 3 else normal) for i, h in enumerate(entetes)]]
    for l in lignes:
        ligne = [Paragraph(l["code"], normal), Paragraph(f"{l['nom']}" + (" <font color='#B91C1C'>(rupture)</font>" if l["statut"] == "rupture" else ""), normal), Paragraph(l["unite"], normal),
                 Paragraph(f"{l['stock']:g}", droite), Paragraph(f"<b>{l['a_commander']}</b>", droite)]
        if avec_prix:
            ligne += [Paragraph("—" if l["prix_unitaire"] is None else f"{l['prix_unitaire']:,}".replace(",", " ") + " F", droite),
                      Paragraph("—" if l["cout_estime"] is None else f"{l['cout_estime']:,}".replace(",", " ") + " F", droite)]
        donnees.append(ligne)
    pied = [Paragraph(f"<b>Total · {len(lignes)} article(s)</b>", normal), "", "", "", ""]
    if avec_prix:
        pied += ["", Paragraph(f"<b>{res['totaux']['cout_estime']:,}".replace(",", " ") + " F</b>", droite_gras)]
    donnees.append(pied)
    larg = [22, 66, 16, 26, 24] + ([24, 28] if avec_prix else [])
    echelle = (180 * mm) / (sum(larg) * mm)
    tableau = Table(donnees, colWidths=[w * mm * echelle for w in larg], repeatRows=1)
    tableau.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")), ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#CBD5E1")),
                                 ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#0A1E3D")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("SPAN", (0, -1), (3, -1)),
                                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    elements.append(tableau)
    if not lignes:
        elements.append(Paragraph("Rien à commander : tous les stocks couvrent la période.", normal))
    elements += [Spacer(1, 14 * mm), Table([[Paragraph("Établi par : " + etabli_par, normal), Paragraph("Validé par (nom, signature, date) :", normal)]], colWidths=[85 * mm, 95 * mm])]
    doc.build(elements)
    return tampon.getvalue()


@routeur.get("/stock/bon-commande")
def bon_de_commande(couverture: int = 30, u: dict = Depends(exiger_roles(roles.ECRITURE_STOCK))):
    """Bon de commande en PDF (affiché dans le lecteur interne) : ce qui est en rupture, urgent ou à commander pour couvrir la période. Journalisé."""
    from .centres import entete_courant
    res = calculer(_couverture(couverture))
    pdf = pdf_bon_de_commande(res, entete_courant(), _voit_les_prix(u), u.get("nom") or u.get("login", ""))
    journaliser("bon_commande_genere", u, f"{res['totaux']['a_commander']} article(s), couverture {couverture} j")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="bon-de-commande.pdf"', "Cache-Control": "no-store"})
