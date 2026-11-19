"""
CONTRÔLE DE L'EAU de dialyse (traitement d'eau : adoucisseur, charbon actif, osmoseur, boucle de distribution) : relevés, seuils, non-conformités et actions correctives.

Les seuils du catalogue ci-dessous sont des valeurs USUELLES (normes de qualité de l'eau pour hémodialyse) : ils sont REGROUPÉS ici et sont À VALIDER par le médecin responsable
et le technicien biomédical, comme les alertes cliniques. Un relevé au-dessus de la limite est NON CONFORME (action corrective obligatoire à documenter) ; au-dessus du seuil
d'alerte il est « à surveiller ». Un contrôle quotidien non fait aujourd'hui, ou une non-conformité non traitée, alimente la pastille du menu. Le serveur alerte, il n'interdit rien.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from . import db, roles, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()

# clé : (libellé, unité, limite, seuil d'alerte, fréquence, point de prélèvement habituel)
TESTS = {
    "chlore_total": ("Chlore total", "mg/L", 0.1, 0.05, "quotidien", "Sortie du charbon actif"),
    "durete": ("Dureté résiduelle", "°f", 1.0, 0.5, "quotidien", "Sortie de l'adoucisseur"),
    "conductivite": ("Conductivité", "µS/cm", 10.0, 5.0, "quotidien", "Sortie de l'osmoseur"),
    "bacterio": ("Bactériologie", "UFC/mL", 100.0, 50.0, "mensuel", "Boucle de distribution (retour)"),
    "endotoxines": ("Endotoxines", "UI/mL", 0.25, 0.125, "mensuel", "Boucle de distribution (retour)"),
}
POINTS = ["Sortie du charbon actif", "Sortie de l'adoucisseur", "Sortie de l'osmoseur", "Boucle de distribution (départ)", "Boucle de distribution (retour)", "Poste de dialyse", "Autre"]
LECTURE = {roles.TECHNICIEN, roles.INFIRMIER, roles.MEDECIN, roles.ADMIN, roles.SUPER_ADMIN}
JOURS_MENSUEL = 35                      # un contrôle mensuel est en retard après 35 jours


def niveau(test: str, valeur: float) -> str:
    """'non_conforme' (> limite), 'alerte' (> seuil d'alerte) ou 'conforme'. Fonction pure."""
    _, _, limite, alerte, _, _ = TESTS[test]
    return "non_conforme" if valeur > limite else "alerte" if valeur > alerte else "conforme"


def _public(c: dict) -> dict:
    return {k: v for k, v in c.items() if k not in ("_id", "centre_id")}


@routeur.get("/eau/listes")
def listes(u: dict = Depends(exiger_roles(LECTURE))):
    return {"tests": [{"cle": k, "libelle": v[0], "unite": v[1], "limite": v[2], "alerte": v[3], "frequence": v[4], "point": v[5]} for k, v in TESTS.items()], "points": POINTS}


@routeur.post("/eau/controles")
def enregistrer(corps: dict, u: dict = Depends(exiger_roles(LECTURE))):
    test = validation.choix(corps, "test", "Contrôle", list(TESTS), obligatoire=True)
    valeur = validation.nombre(corps, "valeur", f"Valeur ({TESTS[test][1]})", 0, 100000)
    if valeur is None:
        validation.erreur("La valeur mesurée est obligatoire")
    jour = validation.date_iso(corps, "date", "Date", False) or date.today().isoformat()
    if jour > date.today().isoformat():
        validation.erreur("La date d'un relevé ne peut pas être dans le futur")
    n = niveau(test, float(valeur))
    doc = {"id": str(uuid.uuid4()), "test": test, "libelle": TESTS[test][0], "unite": TESTS[test][1], "valeur": float(valeur), "date": jour, "point": validation.choix(corps, "point", "Point de prélèvement", POINTS, defaut=TESTS[test][5]),
           "niveau": n, "note": validation.texte(corps, "note", "Note", False, 300), "action": "", "traite": n == "conforme", "par": u["login"], "cree_le": db.maintenant()}
    db.base().controles_eau.insert_one(doc)
    journaliser("eau_releve", u, f"{test} {n}")
    return _public(doc)


@routeur.get("/eau/controles")
def lister(du: str = "", au: str = "", test: str = "", non_traites: bool = False, u: dict = Depends(exiger_roles(LECTURE))):
    f: dict = {}
    if du or au:
        f["date"] = {}
        if du:
            f["date"]["$gte"] = validation.date_iso({"d": du}, "d", "Du")
        if au:
            f["date"]["$lte"] = validation.date_iso({"d": au}, "d", "Au")
    if test:
        f["test"] = test
    if non_traites:
        f["traite"] = False
    return [_public(c) for c in db.base().controles_eau.find(f).sort([("date", -1), ("cree_le", -1)]).limit(500)]


@routeur.put("/eau/controles/{id_}/traiter")
def traiter(id_: str, corps: dict, u: dict = Depends(exiger_roles(LECTURE))):
    """Documente l'ACTION CORRECTIVE d'un relevé non conforme ou à surveiller (obligatoire) : le relevé est alors « traité »."""
    c = db.base().controles_eau.find_one({"id": id_})
    if not c:
        raise HTTPException(404, "Relevé introuvable")
    action = validation.texte(corps, "action", "Action corrective", True, 300)
    db.base().controles_eau.update_one({"id": id_}, {"$set": {"action": action, "traite": True, "traite_par": u["login"], "traite_le": db.maintenant()}})
    journaliser("eau_traite", u, id_)
    return _public(db.base().controles_eau.find_one({"id": id_}))


def etat_du_jour(aujourdhui: date | None = None) -> dict:
    """Par contrôle : dernier relevé et son niveau, fait aujourd'hui ?, en retard ?, série des 30 derniers jours ; + relevés non traités. Une seule lecture de 60 jours."""
    auj = aujourdhui or date.today()
    depuis = (auj - timedelta(days=60)).isoformat()
    releves = list(db.base().controles_eau.find({"date": {"$gte": depuis}}, {"_id": 0, "centre_id": 0}).sort("date", 1))
    res = []
    for cle, (lib, unite, limite, alerte, freq, point) in TESTS.items():
        liste = [r for r in releves if r["test"] == cle]
        dernier = liste[-1] if liste else None
        fait_auj = any(r["date"] == auj.isoformat() for r in liste)
        jours = (auj - date.fromisoformat(dernier["date"])).days if dernier else None
        manquant = (freq == "quotidien" and not fait_auj) or (freq == "mensuel" and (jours is None or jours > JOURS_MENSUEL))
        res.append({"cle": cle, "libelle": lib, "unite": unite, "limite": limite, "alerte": alerte, "frequence": freq, "point": point, "dernier": dernier, "fait_aujourdhui": fait_auj,
                    "manquant": manquant, "serie": [{"date": r["date"], "valeur": r["valeur"], "niveau": r["niveau"]} for r in liste if r["date"] >= (auj - timedelta(days=30)).isoformat()]})
    return {"date": auj.isoformat(), "tests": res, "non_traites": [r for r in releves if not r["traite"]], "manquants": sum(1 for t in res if t["manquant"])}


@routeur.get("/eau/etat")
def etat(u: dict = Depends(exiger_roles(LECTURE))):
    return etat_du_jour()


def a_traiter() -> int:
    """Pastille du menu : contrôles manquants + relevés non traités."""
    e = etat_du_jour()
    return e["manquants"] + len(e["non_traites"])
