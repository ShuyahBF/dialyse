"""
Bilans biologiques : catalogue des paramètres suivis en dialyse, valeurs cibles et interprétation.
Fonctions PURES (sans base de données) : faciles à tester et à ajuster en un seul endroit.
Les cibles sont des valeurs USUELLES de suivi de l'hémodialysé chronique : à valider par le médecin responsable de la clinique.
Chaque paramètre : libellé, unité, cible (mini, maxi) — None = pas de borne —, seuils critiques (bas, haut).
"""
from __future__ import annotations

PARAMETRES = {
    "hemoglobine": {"libelle": "Hémoglobine", "unite": "g/dL", "cible": (10, 12), "critique": (7, None)},
    "potassium": {"libelle": "Potassium", "unite": "mmol/L", "cible": (3.5, 5.5), "critique": (3.0, 6.0)},
    "calcium": {"libelle": "Calcium", "unite": "mmol/L", "cible": (2.1, 2.5), "critique": (1.8, 3.0)},
    "phosphore": {"libelle": "Phosphore", "unite": "mmol/L", "cible": (1.13, 1.78), "critique": (None, None)},
    "pth": {"libelle": "PTH", "unite": "pg/mL", "cible": (150, 600), "critique": (None, None)},
    "sodium": {"libelle": "Sodium", "unite": "mmol/L", "cible": (135, 145), "critique": (125, 155)},
    "bicarbonates": {"libelle": "Bicarbonates", "unite": "mmol/L", "cible": (22, 26), "critique": (15, None)},
    "albumine": {"libelle": "Albumine", "unite": "g/L", "cible": (35, None), "critique": (None, None)},
    "ferritine": {"libelle": "Ferritine", "unite": "µg/L", "cible": (200, 500), "critique": (None, None)},
    "cst": {"libelle": "Saturation de la transferrine", "unite": "%", "cible": (20, 45), "critique": (None, None)},
    "crp": {"libelle": "CRP", "unite": "mg/L", "cible": (None, 5), "critique": (None, None)},
    "glycemie": {"libelle": "Glycémie", "unite": "mmol/L", "cible": (4, 7.8), "critique": (2.8, 20)},
    "creatinine": {"libelle": "Créatinine", "unite": "µmol/L", "cible": (None, None), "critique": (None, None)},
    "uree_pre": {"libelle": "Urée avant dialyse", "unite": "mmol/L", "cible": (None, None), "critique": (None, None)},
    "uree_post": {"libelle": "Urée après dialyse", "unite": "mmol/L", "cible": (None, None), "critique": (None, None)},
}
TYPES_BILAN = ["Mensuel", "Trimestriel", "Semestriel", "Annuel", "Ponctuel"]
URR_CIBLE = 65            # % : taux de réduction de l'urée minimal
JOURS_BILAN_MENSUEL = 35  # au-delà, le bilan mensuel d'un patient actif est « en retard »


def interpreter(cle: str, valeur: float) -> str:
    """'critique_bas' | 'critique_haut' | 'bas' | 'haut' | 'normal' pour une valeur ; 'normal' si le paramètre n'a pas de cible."""
    p = PARAMETRES[cle]
    cb, ch = p["critique"]
    if cb is not None and valeur < cb:
        return "critique_bas"
    if ch is not None and valeur > ch:
        return "critique_haut"
    mini, maxi = p["cible"]
    if mini is not None and valeur < mini:
        return "bas"
    if maxi is not None and valeur > maxi:
        return "haut"
    return "normal"


def urr(uree_pre: float | None, uree_post: float | None) -> float | None:
    """Taux de réduction de l'urée en % : (pré − post) / pré × 100. None si une valeur manque ou si la pré-urée est nulle."""
    if not uree_pre or uree_post is None or uree_pre <= 0:
        return None
    return round((uree_pre - uree_post) / uree_pre * 100, 1)


def analyser(resultats: dict) -> dict:
    """
    Interprétation d'un bilan : {parametre: {valeur, statut}} + URR calculé + liste d'alertes {niveau, message}.
    Niveau « critique » (valeur dangereuse) ou « attention » (hors cible).
    """
    lignes, alertes = {}, []
    for cle, v in resultats.items():
        statut = interpreter(cle, v)
        lignes[cle] = {"valeur": v, "statut": statut}
        p = PARAMETRES[cle]
        if statut.startswith("critique"):
            alertes.append({"niveau": "critique", "message": f"{p['libelle']} critique : {v:g} {p['unite']}"})
        elif statut in ("bas", "haut"):
            alertes.append({"niveau": "attention", "message": f"{p['libelle']} {'basse' if statut == 'bas' else 'haute'} : {v:g} {p['unite']}"})
    taux = urr(resultats.get("uree_pre"), resultats.get("uree_post"))
    if taux is not None and taux < URR_CIBLE:
        alertes.append({"niveau": "attention", "message": f"URR insuffisant : {taux:g} % (cible ≥ {URR_CIBLE} %)"})
    return {"lignes": lignes, "urr": taux, "alertes": alertes}
