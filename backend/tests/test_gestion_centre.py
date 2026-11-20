"""Gestion du centre : planning du personnel, maintenance des postes, contrôle de l'eau, rentabilité."""
import json
from datetime import date, timedelta

from app import db, eau, rentabilite
from conftest import entete, nouveau_patient, nouveau_poste
from test_multi_centres import _centre_b

AUJ = date.today().isoformat()
DEMAIN = (date.today() + timedelta(days=1)).isoformat()


def _equipe(client, h):
    inf = client.post("/personnel", json={"nom": "ILBOUDO Awa", "fonction": "Infirmier(ère)", "cout_mensuel": 150000}, headers=h).json()
    med = client.post("/personnel", json={"nom": "Dr OUEDRAOGO Paul", "fonction": "Néphrologue", "cout_mensuel": 600000}, headers=h).json()
    return inf, med


# ---------- personnel ----------

def test_equipe_affectations_et_conflits(client):
    ha = entete(client, "adm")
    inf, med = _equipe(client, ha)
    assert client.post("/personnel/affectations", json={"personnel_id": inf["id"], "date": DEMAIN, "creneau": "matin"}, headers=ha).status_code == 200
    assert client.post("/personnel/affectations", json={"personnel_id": inf["id"], "date": DEMAIN, "creneau": "matin"}, headers=ha).status_code == 409          # déjà affecté
    assert client.post("/personnel/affectations", json={"personnel_id": inf["id"], "date": DEMAIN, "creneau": "journee", "type": "conge"}, headers=ha).status_code == 409   # présent : retirer d'abord
    assert client.post("/personnel/affectations", json={"personnel_id": med["id"], "date": DEMAIN, "creneau": "journee", "type": "conge"}, headers=ha).status_code == 200
    assert client.post("/personnel/affectations", json={"personnel_id": med["id"], "date": DEMAIN, "creneau": "soir"}, headers=ha).status_code == 409                  # en congé
    assert client.post("/personnel/affectations", json={"personnel_id": med["id"], "date": DEMAIN, "creneau": "journee"}, headers=ha).status_code == 422              # présence = créneau précis
    # droits : le coût d'un salarié n'est vu que de l'administration
    assert client.get("/personnel", headers=entete(client, "inf")).json()[0].get("cout_mensuel") is None
    assert client.get("/personnel", headers=ha).json()[0]["cout_mensuel"] > 0
    assert client.post("/personnel", json={"nom": "X", "fonction": "Autre"}, headers=entete(client, "sec")).status_code == 403


def test_couverture_et_pastille(client):
    ha, hs = entete(client, "adm"), entete(client, "sec")
    inf, med = _equipe(client, ha)
    po = nouveau_poste(client, ha)
    pats = [nouveau_patient(client, hs, nom=f"NOM{i}", telephone="") for i in range(5)]
    postes = [po] + [nouveau_poste(client, ha, f"Poste {i}") for i in range(2, 6)]
    for p, poste in zip(pats, postes):
        client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": DEMAIN, "creneau": "matin"}, headers=hs)
    r = client.get(f"/personnel/planning?du={DEMAIN}&au={DEMAIN}", headers=ha).json()
    c = next(x for x in r["couverture"] if x["creneau"] == "matin")
    assert c["seances"] == 5 and c["soignants_requis"] == 2 and c["manque_soignants"] == 2 and c["sans_medecin"] is True            # 5 patients / 4 = 2 infirmiers, 0 affecté
    assert client.get("/notifications/compteurs", headers=ha).json()["/personnel"] >= 1
    client.post("/personnel/affectations", json={"personnel_id": inf["id"], "date": DEMAIN, "creneau": "matin"}, headers=ha)
    client.post("/personnel/affectations", json={"personnel_id": med["id"], "date": DEMAIN, "creneau": "matin"}, headers=ha)
    c = next(x for x in client.get(f"/personnel/planning?du={DEMAIN}&au={DEMAIN}", headers=ha).json()["couverture"] if x["creneau"] == "matin")
    assert c["manque_soignants"] == 1 and c["sans_medecin"] is False
    assert client.put("/personnel/regles", json={"patients_par_infirmier": 6}, headers=ha).status_code == 200                         # règle réglable : 1 infirmier suffit
    c = next(x for x in client.get(f"/personnel/planning?du={DEMAIN}&au={DEMAIN}", headers=ha).json()["couverture"] if x["creneau"] == "matin")
    assert c["manque_soignants"] == 0


def test_dupliquer_la_semaine(client):
    ha = entete(client, "adm")
    inf, _ = _equipe(client, ha)
    lundi = date.today() - timedelta(days=date.today().weekday())
    client.post("/personnel/affectations", json={"personnel_id": inf["id"], "date": lundi.isoformat(), "creneau": "matin"}, headers=ha)
    suivant = (lundi + timedelta(days=7)).isoformat()
    r = client.post("/personnel/planning/dupliquer", json={"du": lundi.isoformat(), "vers": suivant}, headers=ha).json()
    assert r == {"copiees": 1, "ignorees": 0}
    assert client.post("/personnel/planning/dupliquer", json={"du": lundi.isoformat(), "vers": suivant}, headers=ha).json() == {"copiees": 0, "ignorees": 1}      # déjà fait


# ---------- maintenance ----------

def test_cycle_de_maintenance(client):
    ha, ht = entete(client, "adm"), entete(client, "tec")
    po = nouveau_poste(client, ha)
    r = client.post("/maintenance", json={"poste_id": po["id"], "type": "Maintenance préventive", "date_prevue": AUJ, "prestataire": "BIOMED SARL"}, headers=ht)
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    assert client.get("/postes", headers=ht).json()[0]["prochaine_maintenance"] == AUJ                                              # visible au calendrier
    assert client.get("/notifications/compteurs", headers=ht).json()["/maintenance"] == 1
    assert client.post(f"/maintenance/{mid}/demarrer", headers=ht).status_code == 200
    assert client.get("/postes", headers=ht).json()[0]["statut"] == "maintenance"
    t = client.post(f"/maintenance/{mid}/terminer", json={"cout": 85000, "duree_h": 3, "notes": "Filtres changés"}, headers=ht)
    assert t.status_code == 200
    p = client.get("/postes", headers=ht).json()[0]
    assert p["statut"] == "actif" and p["derniere_maintenance"] == AUJ and p["prochaine_maintenance"] == "" and len(p["maintenances"]) == 1
    assert client.post(f"/maintenance/{mid}/annuler", headers=ht).status_code == 409                                                # déjà terminée
    assert client.get("/maintenance/etat", headers=ht).json()["postes"][0]["seances_depuis_preventive"] == 0


def test_maintenance_refusee_pendant_une_seance(client):
    ha, hs, ht, hi = entete(client, "adm"), entete(client, "sec"), entete(client, "tec"), entete(client, "inf")
    po = nouveau_poste(client, ha)
    p = nouveau_patient(client, hs)
    s = client.post("/seances", json={"patient_id": p["id"], "poste_id": po["id"], "date": AUJ, "creneau": "matin"}, headers=hs).json()
    client.post(f"/seances/{s['id']}/demarrer", json={"pre": {"poids": 70, "tension_sys": 120, "tension_dia": 80}}, headers=hi)
    m = client.post("/maintenance", json={"poste_id": po["id"], "type": "Désinfection chimique", "date_prevue": AUJ}, headers=ht).json()
    assert client.post(f"/maintenance/{m['id']}/demarrer", headers=ht).status_code == 409
    assert client.post("/maintenance", json={"poste_id": po["id"], "type": "Autre", "date_prevue": AUJ}, headers=hs).status_code == 403    # secrétariat : lecture seule


def test_maintenance_en_retard_et_annulation(client):
    ha, ht = entete(client, "adm"), entete(client, "tec")
    po = nouveau_poste(client, ha)
    hier = (date.today() - timedelta(days=3)).isoformat()
    m = client.post("/maintenance", json={"poste_id": po["id"], "type": "Maintenance corrective (panne)", "date_prevue": hier}, headers=ht).json()
    assert m["en_retard"] is True and client.get("/maintenance/etat", headers=ht).json()["en_retard"][0]["id"] == m["id"]
    client.post(f"/maintenance/{m['id']}/annuler", headers=ht)
    assert client.get("/maintenance/etat", headers=ht).json()["en_retard"] == [] and client.get("/postes", headers=ht).json()[0]["prochaine_maintenance"] == ""


# ---------- eau ----------

def test_niveaux_purs():
    assert eau.niveau("chlore_total", 0.02) == "conforme" and eau.niveau("chlore_total", 0.07) == "alerte" and eau.niveau("chlore_total", 0.3) == "non_conforme"
    assert eau.niveau("bacterio", 100) == "alerte" and eau.niveau("bacterio", 101) == "non_conforme"


def test_releves_non_conformite_et_action(client):
    ht = entete(client, "tec")
    assert client.post("/eau/controles", json={"test": "chlore_total", "valeur": 0.02}, headers=ht).json()["niveau"] == "conforme"
    r = client.post("/eau/controles", json={"test": "conductivite", "valeur": 14.5, "note": "Osmoseur à vérifier"}, headers=ht).json()
    assert r["niveau"] == "non_conforme" and r["traite"] is False
    e = client.get("/eau/etat", headers=ht).json()
    assert e["manquants"] == 3 and len(e["non_traites"]) == 1                                                                       # dureté, bactériologie, endotoxines restent à faire
    assert client.put(f"/eau/controles/{r['id']}/traiter", json={}, headers=ht).status_code == 422                                  # action corrective obligatoire
    assert client.put(f"/eau/controles/{r['id']}/traiter", json={"action": "Membranes rincées, nouveau relevé conforme"}, headers=ht).json()["traite"] is True
    assert client.post("/eau/controles", json={"test": "chlore_total", "valeur": 0.01, "date": DEMAIN}, headers=ht).status_code == 422       # pas dans le futur
    assert client.post("/eau/controles", json={"test": "inconnu", "valeur": 1}, headers=ht).status_code == 422
    assert client.get("/eau/etat", headers=entete(client, "sec")).status_code == 403
    assert client.get("/notifications/compteurs", headers=ht).json()["/eau"] >= 1


def test_eau_par_centre(client):
    b, hb = _centre_b(client)
    client.post("/eau/controles", json={"test": "durete", "valeur": 0.2}, headers=entete(client, "tec"))
    assert client.get("/eau/controles", headers=hb).json() == []


# ---------- rentabilité ----------

def test_indicateurs_purs():
    l = {"seances": 100, "facture": 10_000_000, "couts": 8_000_000, "couts_variables": 3_000_000, "couts_fixes": 5_000_000}
    i = rentabilite.indicateurs(l)
    assert i["marge"] == 2_000_000 and i["taux_marge_pct"] == 20.0 and i["cout_par_seance"] == 80_000 and i["recette_par_seance"] == 100_000
    assert i["seuil_seances"] == round(5_000_000 / (100_000 - 30_000))                                                              # 71 séances
    assert rentabilite.indicateurs({"seances": 0, "facture": 0, "couts": 0, "couts_variables": 0, "couts_fixes": 0})["seuil_seances"] is None


def test_rentabilite_par_mois(client):
    ha = entete(client, "adm")
    _equipe(client, ha)                                                                                                            # 750 000 F de salaires par mois
    mois = AUJ[:7]
    client.post("/rentabilite/charges", json={"mois": mois, "categorie": "Loyer", "montant": 400000}, headers=ha)
    client.post("/rentabilite/charges", json={"mois": mois, "categorie": "Consommables et médicaments", "montant": 250000}, headers=ha)
    po = nouveau_poste(client, ha)
    ht = entete(client, "tec")
    m = client.post("/maintenance", json={"poste_id": po["id"], "type": "Maintenance préventive", "date_prevue": AUJ}, headers=ht).json()
    client.post(f"/maintenance/{m['id']}/terminer", json={"cout": 50000}, headers=ht)
    db.base().factures.insert_one({"id": "f1", "numero": "F-1", "date": AUJ, "total": 3_000_000, "paiements": [{"montant": 1_000_000}]})
    r = client.get(f"/rentabilite?de={mois}&a={mois}", headers=ha).json()
    l = r["mois"][0]
    assert l["facture"] == 3_000_000 and l["encaisse"] == 1_000_000 and l["personnel"] == 750_000 and l["maintenance"] == 50_000
    assert l["couts_variables"] == 250_000 and l["couts_fixes"] == 750_000 + 50_000 + 400_000 and l["couts"] == 1_450_000 and l["marge"] == 1_550_000
    assert r["total"]["facture"] == 3_000_000
    # droits : administration et direction ; pas le secrétariat ni les soignants
    assert client.get("/rentabilite", headers=entete(client, "sec")).status_code == 403
    assert client.get("/rentabilite", headers=entete(client, "med")).status_code == 403
    assert client.get("/rentabilite?de=2026-13&a=2026-14", headers=ha).status_code == 422
    assert client.get("/rentabilite?de=2024-01&a=2026-12", headers=ha).status_code == 422                                          # plus de 24 mois
    assert client.post("/rentabilite/charges", json={"mois": mois, "categorie": "Autre", "montant": 0}, headers=ha).status_code == 422


def test_rentabilite_par_defaut_six_mois(client):
    r = client.get("/rentabilite", headers=entete(client, "adm")).json()
    assert len(r["mois"]) == 6 and r["mois"][-1]["mois"] == AUJ[:7]


# ---------- consommables valorisés (lot 27) ----------

def _article_et_lot(client, h, cout=None):
    """Un article « par séance » et une réception de 10 pièces dans le lot LOT-V1 (prix unitaire facultatif)."""
    a = client.post("/stock/articles", json={"nom": "Dialyseur FX60", "categorie": "Dialyseur", "unite": "pièce", "seuil_alerte": 2, "par_seance": 0}, headers=h).json()
    corps = {"article_id": a["id"], "quantite": 10, "lot": "LOT-V1", "peremption": "2031-01-01"}
    if cout is not None:
        corps["cout_unitaire"] = cout
    r = client.post("/stock/entrees", json=corps, headers=h)
    assert r.status_code == 200, r.text
    return a


def test_sortie_valorisee_dans_la_rentabilite(client):
    ha = entete(client, "adm")
    a = _article_et_lot(client, ha, cout=12500)
    mois = AUJ[:7]
    sortie = client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 4}, headers=ha).json()
    assert sortie["valeur"] == 50000 and sortie["sans_prix"] == 0                       # 4 x 12 500 FCFA
    client.post("/rentabilite/charges", json={"mois": mois, "categorie": "Consommables et médicaments", "montant": 100000}, headers=ha)
    r = client.get(f"/rentabilite?de={mois}&a={mois}", headers=ha).json()["mois"][0]
    assert r["consommables_stock"] == 50000 and r["conso_sans_prix"] == 0
    assert r["couts_variables"] == 150000                                               # stock valorisé + charge saisie : tous deux variables
    perte = client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 1, "type": "perte", "motif": "Casse"}, headers=ha).json()
    assert perte["valeur"] == 12500                                                     # une perte est aussi un coût
    assert client.get(f"/rentabilite?de={mois}&a={mois}", headers=ha).json()["total"]["consommables_stock"] == 62500


def test_sortie_sans_prix_signalee_et_non_comptee(client):
    ha = entete(client, "adm")
    a = _article_et_lot(client, ha)                                                     # lot sans prix
    mois = AUJ[:7]
    s = client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 3}, headers=ha).json()
    assert s["valeur"] == 0 and s["sans_prix"] == 3
    r = client.get(f"/rentabilite?de={mois}&a={mois}", headers=ha).json()["mois"][0]
    assert r["consommables_stock"] == 0 and r["conso_sans_prix"] == 3                   # signalé à l'écran, jamais deviné


def test_prix_d_un_lot_existant(client):
    ha = entete(client, "adm")
    a = _article_et_lot(client, ha, cout=1000)
    meme = {"article_id": a["id"], "quantite": 2, "lot": "LOT-V1", "cout_unitaire": 1000}
    assert client.post("/stock/entrees", json=meme, headers=ha).status_code == 200
    assert client.post("/stock/entrees", json={**meme, "cout_unitaire": 1200}, headers=ha).status_code == 409         # un lot garde son prix
    assert client.post("/stock/entrees", json={**meme, "cout_unitaire": -5}, headers=ha).status_code == 422


def test_les_prix_ne_sont_vus_que_de_l_administration(client):
    ha, hi = entete(client, "adm"), entete(client, "inf")
    a = _article_et_lot(client, ha, cout=12500)
    client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 1}, headers=ha)
    for h, vu in ((ha, True), (hi, False)):
        detail = client.get(f"/stock/articles/{a['id']}/lots", headers=h).json()
        mouvements = client.get("/stock/mouvements", headers=h).json()
        assert ("cout_unitaire" in detail["lots"][0]) is vu
        assert all(("valeur" in m) is vu for m in mouvements if m["type"] == "sortie")
        assert all("cout_unitaire" not in json.dumps(m.get("lots", [])) for m in mouvements)   # jamais dans la liste des lots utilisés
    # un infirmier peut RECEVOIR du stock avec un prix mais ne le revoit pas
    r = client.post("/stock/entrees", json={"article_id": a["id"], "quantite": 1, "lot": "LOT-V2", "cout_unitaire": 900}, headers=hi)
    assert r.status_code == 200 and "cout_unitaire" not in r.json()
