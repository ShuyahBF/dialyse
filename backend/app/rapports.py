"""
Rapports d'activité : par jour, semaine ou mois, sur une période libre, par genre et par tranche d'âge.
Tous les chiffres sont AGRÉGÉS : aucun nom ni code de patient (la direction peut donc les consulter).
Les fonctions de calcul sont PURES (sans base de données) : testées sans serveur.
Une séance « réalisée » est terminée ou en cours ; le taux d'absence = absents / (réalisées + absents).
"""
from __future__ import annotations

import io
from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from . import db, roles, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()
REGROUPEMENTS = ["jour", "semaine", "mois"]
TRANCHES = [(0, 14, "0-14 ans"), (15, 24, "15-24 ans"), (25, 34, "25-34 ans"), (35, 44, "35-44 ans"), (45, 54, "45-54 ans"),
            (55, 64, "55-64 ans"), (65, 74, "65-74 ans"), (75, 200, "75 ans et +")]
SEUIL_KTV = 1.2
MAX_JOURS = 366


# ---------- fonctions pures ----------

def tranche_age(age: int | None) -> str:
    """Libellé de la tranche d'âge (« Âge inconnu » si la date de naissance manque)."""
    if age is None:
        return "Âge inconnu"
    for mini, maxi, libelle in TRANCHES:
        if mini <= age <= maxi:
            return libelle
    return "Âge inconnu"


def age_a(naissance: str, jour: str) -> int | None:
    """Âge en années complètes à la date `jour` (AAAA-MM-JJ) ; None si une date est illisible."""
    try:
        n, j = date.fromisoformat(naissance), date.fromisoformat(jour)
    except (ValueError, TypeError):
        return None
    return j.year - n.year - ((j.month, j.day) < (n.month, n.day))


def cle_periode(jour: str, regroupement: str) -> str:
    """Clé de regroupement : la date (jour), le lundi de la semaine (semaine) ou « AAAA-MM » (mois)."""
    if regroupement == "mois":
        return jour[:7]
    if regroupement == "semaine":
        d = date.fromisoformat(jour)
        return (d - timedelta(days=d.weekday())).isoformat()
    return jour


def realisee(s: dict) -> bool:
    return s["statut"] in ("terminee", "en_cours")


def moyenne(valeurs: list[float], decimales: int = 1) -> float | None:
    return round(sum(valeurs) / len(valeurs), decimales) if valeurs else None


def indicateurs(seances: list[dict]) -> dict:
    """Indicateurs d'un ensemble de séances : réalisées, absents, annulées, patients distincts, durée / UF / Kt/V moyens, incidents."""
    faites = [s for s in seances if realisee(s)]
    absents = sum(1 for s in seances if s["statut"] == "absente")
    posts = [s.get("post") or {} for s in faites]
    ktv = [p["kt_v"] for p in posts if p.get("kt_v") is not None]
    return {"realisees": len(faites), "absents": absents, "annulees": sum(1 for s in seances if s["statut"] == "annulee"),
            "planifiees": sum(1 for s in seances if s["statut"] == "planifiee"), "patients": len({s["patient_id"] for s in faites}),
            "taux_absence_pct": round(100 * absents / (len(faites) + absents), 1) if (faites or absents) else 0.0,
            "duree_moyenne_min": moyenne([p["duree_reelle_min"] for p in posts if p.get("duree_reelle_min")], 0),
            "uf_moyenne_l": moyenne([p["volume_uf_l"] for p in posts if p.get("volume_uf_l") is not None], 2),
            "ktv_moyen": moyenne(ktv, 2), "ktv_conforme_pct": round(100 * sum(1 for k in ktv if k >= SEUIL_KTV) / len(ktv), 1) if ktv else None,
            "incidents": sum(len(s.get("incidents") or []) for s in faites)}


def serie(seances: list[dict], regroupement: str) -> list[dict]:
    """Évolution par période (triée) : séances réalisées, patients distincts, absents, incidents."""
    groupes: dict = defaultdict(list)
    for s in seances:
        groupes[cle_periode(s["date"], regroupement)].append(s)
    res = []
    for cle in sorted(groupes):
        i = indicateurs(groupes[cle])
        res.append({"periode": cle, "realisees": i["realisees"], "patients": i["patients"], "absents": i["absents"], "incidents": i["incidents"]})
    return res


def demographie(seances: list[dict], patients: dict) -> dict:
    """Répartition des séances réalisées par genre et par tranche d'âge (âge calculé à la date de chaque séance)."""
    genre_p, genre_s = defaultdict(set), Counter()
    tr_p, tr_s, ktv_tr = defaultdict(set), Counter(), defaultdict(list)
    croise: dict = defaultdict(lambda: defaultdict(set))
    for s in seances:
        if not realisee(s):
            continue
        p = patients.get(s["patient_id"]) or {}
        sexe = p.get("sexe") or "?"
        tr = tranche_age(age_a(p.get("date_naissance", ""), s["date"]))
        genre_p[sexe].add(s["patient_id"]); genre_s[sexe] += 1
        tr_p[tr].add(s["patient_id"]); tr_s[tr] += 1
        croise[tr][sexe].add(s["patient_id"])
        k = (s.get("post") or {}).get("kt_v")
        if k is not None:
            ktv_tr[tr].append(k)
    ordre = [t[2] for t in TRANCHES] + ["Âge inconnu"]
    return {"genre": [{"genre": g, "libelle": {"F": "Femmes", "M": "Hommes"}.get(g, "Non précisé"), "patients": len(genre_p[g]), "seances": genre_s[g]} for g in sorted(genre_p)],
            "tranches": [{"tranche": t, "patients": len(tr_p[t]), "seances": tr_s[t], "ktv_moyen": moyenne(ktv_tr[t], 2)} for t in ordre if t in tr_p],
            "croise": [{"tranche": t, "femmes": len(croise[t].get("F", ())), "hommes": len(croise[t].get("M", ()))} for t in ordre if t in croise]}


# ---------- routes ----------

def _periode(du: str, au: str) -> tuple[str, str]:
    du, au = validation.date_iso({"d": du}, "d", "Du", True), validation.date_iso({"d": au}, "d", "Au", True)
    if au < du:
        validation.erreur("Période invalide : la fin précède le début")
    if (date.fromisoformat(au) - date.fromisoformat(du)).days >= MAX_JOURS:
        validation.erreur(f"Période trop longue ({MAX_JOURS} jours au plus)")
    return du, au


def _donnees(du: str, au: str) -> tuple[list[dict], dict]:
    """Séances de la période et patients concernés, lus EN BLOC (une requête par collection : règle 7)."""
    seances = list(db.base().seances.find({"date": {"$gte": du, "$lte": au}}, {"_id": 0}))
    pids = list({s["patient_id"] for s in seances})
    patients = {p["id"]: p for p in db.base().patients.find({"id": {"$in": pids}}, {"_id": 0, "id": 1, "sexe": 1, "date_naissance": 1})} if pids else {}
    return seances, patients


def construire(du: str, au: str, regroupement: str) -> dict:
    seances, patients = _donnees(du, au)
    postes = {p["id"]: p["nom"] for p in db.base().postes.find({}, {"id": 1, "nom": 1})}
    par_poste: dict = defaultdict(list)
    par_creneau: dict = defaultdict(list)
    types_incident: Counter = Counter()
    for s in seances:
        par_poste[s["poste_id"]].append(s)
        par_creneau[s["creneau"]].append(s)
        if realisee(s):
            types_incident.update(i["type"] for i in s.get("incidents") or [])
    return {"du": du, "au": au, "regroupement": regroupement, "totaux": indicateurs(seances), "serie": serie(seances, regroupement),
            "par_poste": sorted([{"poste": postes.get(pid, "?"), "realisees": indicateurs(l)["realisees"], "absents": indicateurs(l)["absents"]} for pid, l in par_poste.items()], key=lambda x: x["poste"]),
            "par_creneau": [{"creneau": c, "realisees": indicateurs(par_creneau[c])["realisees"]} for c in ("matin", "midi", "soir") if c in par_creneau],
            "incidents": [{"type": t, "nombre": n} for t, n in types_incident.most_common()],
            "demographie": demographie(seances, patients),
            "patients_actifs": db.base().patients.count_documents({"statut": "actif"})}


@routeur.get("/rapports/activite")
def activite(du: str, au: str, regroupement: str = "jour", u: dict = Depends(exiger_roles(roles.LECTURE_RAPPORTS))):
    """Rapport d'activité d'une période (jour, semaine ou mois), avec séries, postes, créneaux, incidents, genre et tranches d'âge. Agrégé."""
    if regroupement not in REGROUPEMENTS:
        validation.erreur("Regroupement : jour, semaine ou mois")
    du, au = _periode(du, au)
    journaliser("rapport_consulte", u, f"{du} → {au} ({regroupement})")
    return construire(du, au, regroupement)


def pdf_rapport(r: dict, clinique: dict) -> bytes:
    """PDF du rapport (reportlab) : indicateurs, série, postes, incidents, genre et tranches d'âge. Nombres alignés à droite."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title="Rapport d'activité")
    st = getSampleStyleSheet()
    titre = ParagraphStyle("t", parent=st["Title"], textColor=colors.HexColor("#0A1E3D"), alignment=0)

    def tableau(entete, lignes, largeurs):
        t = Table([entete] + lignes, colWidths=[l * mm for l in largeurs], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                               ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5)]))
        return t
    fr = lambda d: f"{d[8:]}/{d[5:7]}/{d[:4]}"
    t = r["totaux"]
    n = lambda v, suffixe="": "—" if v is None else f"{v:g}".replace(".", ",") + suffixe
    from .centres import element_logo
    logo = element_logo(clinique, 14)
    el = ([logo, Spacer(1, 2 * mm)] if logo else []) + [Paragraph(clinique.get("nom") or "Clinique de dialyse", titre), Paragraph(f"<b>Rapport d'activité</b> du {fr(r['du'])} au {fr(r['au'])} (regroupement par {r['regroupement']})", st["Heading3"]), Spacer(1, 3 * mm),
          tableau(["Indicateur", "Valeur"], [["Séances réalisées", n(t["realisees"])], ["Patients traités", n(t["patients"])], ["Patients absents (séances)", n(t["absents"])],
                                              ["Taux d'absence", n(t["taux_absence_pct"], " %")], ["Séances annulées", n(t["annulees"])], ["Durée moyenne", n(t["duree_moyenne_min"], " min")],
                                              ["Ultrafiltration moyenne", n(t["uf_moyenne_l"], " l")], ["Kt/V moyen", n(t["ktv_moyen"])], ["Kt/V ≥ 1,2", n(t["ktv_conforme_pct"], " %")],
                                              ["Incidents déclarés", n(t["incidents"])]], [110, 40]), Spacer(1, 4 * mm),
          Paragraph("<b>Évolution</b>", st["Normal"]),
          tableau(["Période", "Séances", "Patients", "Absents", "Incidents"], [[fr(x["periode"]) if len(x["periode"]) == 10 else x["periode"], x["realisees"], x["patients"], x["absents"], x["incidents"]] for x in r["serie"]], [60, 30, 30, 30, 30]),
          Spacer(1, 4 * mm), Paragraph("<b>Par poste</b>", st["Normal"]), tableau(["Poste", "Séances", "Absents"], [[x["poste"], x["realisees"], x["absents"]] for x in r["par_poste"]], [90, 40, 40])]
    d = r["demographie"]
    el += [Spacer(1, 4 * mm), Paragraph("<b>Par genre</b>", st["Normal"]), tableau(["Genre", "Patients", "Séances"], [[x["libelle"], x["patients"], x["seances"]] for x in d["genre"]], [90, 40, 40]),
           Spacer(1, 4 * mm), Paragraph("<b>Par tranche d'âge</b>", st["Normal"]),
           tableau(["Tranche", "Patients", "Séances", "Kt/V moyen"], [[x["tranche"], x["patients"], x["seances"], n(x["ktv_moyen"])] for x in d["tranches"]], [70, 30, 30, 30])]
    if r["incidents"]:
        el += [Spacer(1, 4 * mm), Paragraph("<b>Incidents par type</b>", st["Normal"]), tableau(["Type", "Nombre"], [[x["type"], x["nombre"]] for x in r["incidents"]], [110, 40])]
    el += [Spacer(1, 6 * mm), Paragraph("Rapport agrégé : aucune donnée nominative.", st["Italic"])]
    doc.build(el)
    return tampon.getvalue()


@routeur.get("/rapports/pdf")
def pdf(du: str, au: str, regroupement: str = "jour", u: dict = Depends(exiger_roles(roles.LECTURE_RAPPORTS))):
    """PDF du rapport, servi en « inline » (lecteur interne de l'application, jamais téléchargé)."""
    if regroupement not in REGROUPEMENTS:
        validation.erreur("Regroupement : jour, semaine ou mois")
    du, au = _periode(du, au)
    journaliser("rapport_pdf", u, f"{du} → {au}")
    from .centres import entete_courant
    clinique = entete_courant()
    return Response(pdf_rapport(construire(du, au, regroupement), clinique), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="rapport_{du}_{au}.pdf"'})
