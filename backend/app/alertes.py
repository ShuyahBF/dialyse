"""
Alertes cliniques calculées à partir des constantes d'une séance (aide à la décision : elles n'interdisent rien, elles alertent).
Fonctions PURES (sans accès à la base) : faciles à tester.
Seuils usuels, à valider par le médecin responsable : ils sont regroupés ici pour être ajustés au même endroit.
"""
from __future__ import annotations

SEUIL_HYPOTENSION_SYS = 100          # mmHg, début de séance
SEUIL_HYPOTENSION_PER = 90           # mmHg, pendant la séance
SEUIL_HYPERTENSION_SYS = 180         # mmHg
SEUIL_FIEVRE = 38.0                  # °C
SEUIL_GAIN_POIDS = 0.04              # 4 % du poids sec : prise de poids interdialytique élevée
SEUIL_KTV = 1.2                      # dose de dialyse minimale
SEUIL_UFR = 13.0                     # ml/kg/h : débit d'ultrafiltration maximal conseillé
SEUIL_DUREE = 0.9                    # 90 % de la durée prescrite


def alertes_seance(seance: dict, poids_sec: float | None) -> list[dict]:
    """Liste d'alertes {niveau: 'critique'|'attention', message} d'une séance."""
    a: list[dict] = []
    pre, post, par = seance.get("pre") or {}, seance.get("post") or {}, seance.get("parametres") or {}

    def ajoute(niveau: str, msg: str):
        a.append({"niveau": niveau, "message": msg})

    if pre.get("tension_sys") is not None and pre["tension_sys"] < SEUIL_HYPOTENSION_SYS:
        ajoute("critique", f"Hypotension en début de séance ({pre['tension_sys']:g} mmHg)")
    if pre.get("tension_sys") is not None and pre["tension_sys"] >= SEUIL_HYPERTENSION_SYS:
        ajoute("critique", f"Hypertension sévère en début de séance ({pre['tension_sys']:g} mmHg)")
    if pre.get("temperature") is not None and pre["temperature"] >= SEUIL_FIEVRE:
        ajoute("critique", f"Fièvre en début de séance ({pre['temperature']:g} °C)")
    if poids_sec and pre.get("poids") is not None:
        gain = pre["poids"] - poids_sec
        if gain > SEUIL_GAIN_POIDS * poids_sec:
            ajoute("attention", f"Prise de poids élevée : +{gain:.1f} kg au-dessus du poids sec ({100 * gain / poids_sec:.1f} %)")
    for m in seance.get("surveillance") or []:
        if m.get("tension_sys") is not None and m["tension_sys"] < SEUIL_HYPOTENSION_PER:
            ajoute("critique", f"Hypotension pendant la séance ({m['tension_sys']:g} mmHg à {m.get('heure', '?')})")
            break
    if post.get("kt_v") is not None and post["kt_v"] < SEUIL_KTV:
        ajoute("attention", f"Dose de dialyse insuffisante (Kt/V {post['kt_v']:g} < {SEUIL_KTV:g})")
    prevue, reelle = par.get("duree_prevue_min"), post.get("duree_reelle_min")
    if prevue and reelle and reelle < SEUIL_DUREE * prevue:
        ajoute("attention", f"Séance écourtée : {reelle:g} min au lieu de {prevue:g} min")
    poids_ref = post.get("poids") or pre.get("poids")
    if post.get("volume_uf_l") and reelle and poids_ref:
        ufr = post["volume_uf_l"] * 1000 / (reelle / 60) / poids_ref
        if ufr > SEUIL_UFR:
            ajoute("attention", f"Ultrafiltration rapide : {ufr:.1f} ml/kg/h (maximum conseillé {SEUIL_UFR:g})")
    if seance.get("incidents"):
        ajoute("attention", f"{len(seance['incidents'])} incident(s) déclaré(s)")
    return a


def alerte_isolement(serologies: dict | None, poste_isole: bool) -> str | None:
    """Alerte de planification : patient à sérologie positive sur un poste non isolé."""
    positives = [k.upper() for k, v in (serologies or {}).items() if v == "positif"]
    if positives and not poste_isole:
        return "Sérologie positive (" + ", ".join(positives) + ") : ce poste n'est pas un poste d'isolement"
    return None
