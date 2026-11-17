"""Rapports : fonctions pures (périodes, âge, tranches), agrégats, genre / tranches d'âge, droits (direction), anonymat, PDF."""
from datetime import date

from app import rapports as rp
from conftest import entete, nouveau_patient, nouveau_poste


def test_fonctions_pures():
    assert rp.tranche_age(0) == "0-14 ans" and rp.tranche_age(14) == "0-14 ans" and rp.tranche_age(15) == "15-24 ans"
    assert rp.tranche_age(74) == "65-74 ans" and rp.tranche_age(75) == "75 ans et +" and rp.tranche_age(None) == "Âge inconnu"
    assert rp.age_a("1975-03-02", "2026-03-01") == 50 and rp.age_a("1975-03-02", "2026-03-02") == 51 and rp.age_a("", "2026-01-01") is None
    assert rp.cle_periode("2030-01-09", "jour") == "2030-01-09" and rp.cle_periode("2030-01-09", "mois") == "2030-01"
    assert rp.cle_periode("2030-01-09", "semaine") == "2030-01-07" and rp.cle_periode("2030-01-13", "semaine") == "2030-01-07"     # lundi 7 → dimanche 13
    assert rp.moyenne([]) is None and rp.moyenne([1, 2, 4], 2) == 2.33


def test_indicateurs_purs():
    s = [{"statut": "terminee", "patient_id": "a", "post": {"kt_v": 1.4, "duree_reelle_min": 240, "volume_uf_l": 2.0}, "incidents": [{"type": "Crampes"}]},
         {"statut": "terminee", "patient_id": "b", "post": {"kt_v": 1.0, "duree_reelle_min": 200, "volume_uf_l": 3.0}},
         {"statut": "absente", "patient_id": "c"}, {"statut": "annulee", "patient_id": "d"}, {"statut": "planifiee", "patient_id": "e"}]
    i = rp.indicateurs(s)
    assert (i["realisees"], i["absents"], i["annulees"], i["planifiees"], i["patients"]) == (2, 1, 1, 1, 2)
    assert i["taux_absence_pct"] == 33.3 and i["duree_moyenne_min"] == 220 and i["uf_moyenne_l"] == 2.5 and i["ktv_moyen"] == 1.2 and i["ktv_conforme_pct"] == 50.0 and i["incidents"] == 1
    vide = rp.indicateurs([])
    assert vide["realisees"] == 0 and vide["taux_absence_pct"] == 0.0 and vide["ktv_moyen"] is None and vide["ktv_conforme_pct"] is None


def _seance_terminee(client, h, hi, pid, poste, jour, creneau, kt=1.3):
    sid = client.post("/seances", json={"patient_id": pid, "poste_id": poste, "date": jour, "creneau": creneau}, headers=h).json()["id"]
    client.post(f"/seances/{sid}/demarrer", json={"pre": {"poids": 60, "tension_sys": 120, "tension_dia": 80}}, headers=hi)
    client.post(f"/seances/{sid}/terminer", json={"post": {"poids": 58, "kt_v": kt, "duree_reelle_min": 240, "volume_uf_l": 2}}, headers=hi)
    return sid


def _jeu(client):
    """Deux femmes (51 et 22 ans) et un homme (65 ans) ; 4 séances terminées, 1 absence, sur 2 semaines."""
    hm, hi, ha = entete(client, "med"), entete(client, "inf"), entete(client, "adm")
    poste1, poste2 = nouveau_poste(client, ha, "Poste 1")["id"], nouveau_poste(client, ha, "Poste 2")["id"]
    f1 = nouveau_patient(client, hm, nom="Alpha", prenom="A", sexe="F", date_naissance="1975-03-02")
    f2 = nouveau_patient(client, hm, nom="Bravo", prenom="B", sexe="F", date_naissance="2004-06-15")
    h1 = nouveau_patient(client, hm, nom="Charlie", prenom="C", sexe="M", date_naissance="1965-01-20")
    _seance_terminee(client, hm, hi, f1["id"], poste1, "2030-01-07", "matin")
    _seance_terminee(client, hm, hi, f2["id"], poste2, "2030-01-07", "matin", kt=1.0)
    _seance_terminee(client, hm, hi, h1["id"], poste1, "2030-01-09", "midi")
    _seance_terminee(client, hm, hi, f1["id"], poste1, "2030-01-14", "matin")
    sid = client.post("/seances", json={"patient_id": h1["id"], "poste_id": poste2, "date": "2030-01-14", "creneau": "soir"}, headers=hm).json()["id"]
    client.post(f"/seances/{sid}/annuler", json={"absent": True}, headers=hm)
    return hm


def test_rapport_par_jour_semaine_mois(client):
    hm = _jeu(client)
    r = client.get("/rapports/activite?du=2030-01-01&au=2030-01-31&regroupement=jour", headers=hm).json()
    assert r["totaux"]["realisees"] == 4 and r["totaux"]["absents"] == 1 and r["totaux"]["patients"] == 3
    assert [(x["periode"], x["realisees"]) for x in r["serie"]] == [("2030-01-07", 2), ("2030-01-09", 1), ("2030-01-14", 1)]
    sem = client.get("/rapports/activite?du=2030-01-01&au=2030-01-31&regroupement=semaine", headers=hm).json()["serie"]
    assert [(x["periode"], x["realisees"], x["absents"]) for x in sem] == [("2030-01-07", 3, 0), ("2030-01-14", 1, 1)]
    mois = client.get("/rapports/activite?du=2030-01-01&au=2030-01-31&regroupement=mois", headers=hm).json()["serie"]
    assert [(x["periode"], x["realisees"]) for x in mois] == [("2030-01", 4)]
    # sur une période libre plus courte : seulement la première semaine
    court = client.get("/rapports/activite?du=2030-01-07&au=2030-01-09", headers=hm).json()
    assert court["totaux"]["realisees"] == 3 and court["totaux"]["absents"] == 0
    assert {x["poste"]: x["realisees"] for x in r["par_poste"]} == {"Poste 1": 3, "Poste 2": 1}
    assert {x["creneau"]: x["realisees"] for x in r["par_creneau"]} == {"matin": 3, "midi": 1, "soir": 0}      # le créneau du soir n a que l absent


def test_rapport_genre_et_tranches(client):
    hm = _jeu(client)
    d = client.get("/rapports/activite?du=2030-01-01&au=2030-01-31", headers=hm).json()["demographie"]
    assert {x["libelle"]: (x["patients"], x["seances"]) for x in d["genre"]} == {"Femmes": (2, 3), "Hommes": (1, 1)}
    # âges à la date des séances (janvier 2030) : 54 ans (1975), 25 ans (2004), 64 ans (1965, anniversaire le 20 : 64 le 9 janvier)
    tr = {x["tranche"]: (x["patients"], x["seances"]) for x in d["tranches"]}
    assert tr == {"25-34 ans": (1, 1), "45-54 ans": (1, 2), "55-64 ans": (1, 1)}
    assert {x["tranche"]: (x["femmes"], x["hommes"]) for x in d["croise"]} == {"25-34 ans": (1, 0), "45-54 ans": (1, 0), "55-64 ans": (0, 1)}
    ktv = {x["tranche"]: x["ktv_moyen"] for x in d["tranches"]}
    assert ktv["25-34 ans"] == 1.0 and ktv["45-54 ans"] == 1.3


def test_validations(client):
    hm = entete(client, "med")
    assert client.get("/rapports/activite?du=2030-02-01&au=2030-01-01", headers=hm).status_code == 422
    assert client.get("/rapports/activite?du=2030-01-01&au=2031-06-01", headers=hm).status_code == 422          # plus de 366 jours
    assert client.get("/rapports/activite?du=2030-01-01&au=2030-01-31&regroupement=annee", headers=hm).status_code == 422
    assert client.get("/rapports/activite?du=abc&au=2030-01-31", headers=hm).status_code == 422
    vide = client.get("/rapports/activite?du=2030-01-01&au=2030-01-31", headers=hm).json()
    assert vide["totaux"]["realisees"] == 0 and vide["serie"] == [] and vide["demographie"]["genre"] == []


def test_droits_direction_anonymat_et_journal(client):
    ha = entete(client, "adm")
    hm = _jeu(client)
    # le directeur général : rapports et tableau de bord agrégés, mais aucun accès nominatif
    assert client.post("/utilisateurs", json={"login": "dg", "nom_affiche": "BADINI Awa", "role": "direction", "mot_de_passe": "Provisoire1"}, headers=ha).status_code == 200
    hd = {"Authorization": "Bearer " + client.post("/auth/login", json={"login": "dg", "mot_de_passe": "Provisoire1"}).json()["jeton"]}
    r = client.get("/rapports/activite?du=2030-01-01&au=2030-01-31", headers=hd)
    assert r.status_code == 200 and r.json()["totaux"]["realisees"] == 4
    texte = r.text.lower()
    for nom in ("alpha", "bravo", "charlie", "dial-0"):
        assert nom not in texte                                                                                 # aucun nom ni code de patient dans un rapport
    assert client.get("/tableau", headers=hd).status_code == 200
    for chemin in ("/patients", "/seances", "/bilans/suivi", "/stock/articles", "/factures", "/utilisateurs", "/journal"):
        assert client.get(chemin, headers=hd).status_code in (403,), chemin
    assert client.get("/rapports/activite?du=2030-01-01&au=2030-01-31", headers=entete(client, "sec")).status_code == 403
    assert client.get("/rapports/activite?du=2030-01-01&au=2030-01-31", headers=entete(client, "tec")).status_code == 403
    assert any(l["acteur"] == "dg" for l in client.get("/journal?action=rapport_consulte", headers=ha).json())


def test_pdf(client):
    hm = _jeu(client)
    r = client.get("/rapports/pdf?du=2030-01-01&au=2030-01-31&regroupement=semaine", headers=hm)
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and "inline" in r.headers["content-disposition"]
    assert client.get("/rapports/pdf?du=2030-01-01&au=2030-01-31", headers=entete(client, "sec")).status_code == 403
