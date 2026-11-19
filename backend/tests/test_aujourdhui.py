"""Tableau de bord « Aujourd'hui » : état des dialyses en direct par poste, retards, fins proches, droits, étanchéité entre centres, pastille du menu."""
from datetime import date, datetime, timedelta, timezone

from app import aujourdhui, db
from conftest import CENTRE, entete, nouveau_patient, nouveau_poste
from test_multi_centres import _centre_b

AUJ = date.today().isoformat()


def _t(h, m=0):
    return datetime.fromisoformat(f"{AUJ}T{h:02d}:{m:02d}:00+00:00")


def _prep(client):
    h = entete(client, "sec")
    p = nouveau_patient(client, h, telephone="70123456")
    po = nouveau_poste(client, entete(client, "adm"))
    return h, p, po


def _seance(client, h, p, po, creneau="matin"):
    r = client.post("/seances", json={"patient_id": p["id"], "poste_id": po["id"], "date": AUJ, "creneau": creneau}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_poste_libre_puis_en_retard_puis_en_cours(client):
    h, p, po = _prep(client)
    s = _seance(client, h, p, po)                                                      # séance du matin, 07:00
    r = aujourdhui.calculer(_t(6, 0), "admin")
    assert r["postes_libres"] == 1 and r["postes_occupes"] == 0 and r["a_venir"][0]["heure"] == "07:00" and r["en_retard"] == []
    assert r["postes"][0]["prochaine"]["patient"]["code"] == p["code"]
    r = aujourdhui.calculer(_t(7, 20), "admin")                                         # 20 minutes après l'heure : en retard
    assert r["en_retard"][0]["retard_min"] == 20 and r["a_venir"] == []
    assert aujourdhui.nombre_en_retard(_t(7, 20)) == 1 and aujourdhui.nombre_en_retard(_t(7, 10)) == 0
    # démarrage : le poste devient occupé, avec temps restant et progression
    hi = entete(client, "inf")
    d = client.post(f"/seances/{s['id']}/demarrer", json={"pre": {"poids": 70, "tension_sys": 120, "tension_dia": 80}, "duree_prevue_min": 240}, headers=hi)
    assert d.status_code == 200, d.text
    # heure de début FIXÉE (08:00) : le test ne dépend pas de l'heure réelle d'exécution (ni du passage de minuit)
    debut = _t(8, 0)
    db.base().seances.update_one({"id": s["id"]}, {"$set": {"debut_a": debut.isoformat()}})
    r = aujourdhui.calculer(debut + timedelta(minutes=60), "admin")
    c = r["postes"][0]["en_cours"]
    assert r["postes_occupes"] == 1 and c["ecoule_min"] == 60 and c["restant_min"] == 180 and c["progression_pct"] == 25 and c["fin_prevue"] == "12:00"
    assert r["en_retard"] == [] and r["fin_proche"] == []
    r = aujourdhui.calculer(_t(11, 40), "admin")
    assert r["fin_proche"][0]["restant_min"] == 20                                     # se termine bientôt
    r = aujourdhui.calculer(_t(12, 10), "admin")
    assert r["depassees"] and r["postes"][0]["en_cours"]["depasse"] is True            # durée prévue dépassée


def test_secretariat_sans_detail_medical_et_comptes(client):
    h, p, po = _prep(client)
    s = _seance(client, h, p, po)
    client.post(f"/seances/{s['id']}/demarrer", json={"pre": {"poids": 70, "tension_sys": 60, "tension_dia": 40}}, headers=entete(client, "inf"))   # tension basse : alerte clinique
    r_sec = client.get("/aujourdhui", headers=h).json()
    c = r_sec["postes"][0]["en_cours"]
    assert c["alertes"] == [] and r_sec["a_valider"] is None                           # le secrétariat ne reçoit aucune alerte clinique
    r_inf = client.get("/aujourdhui", headers=entete(client, "inf")).json()
    assert r_inf["postes"][0]["en_cours"]["alertes"] and r_inf["comptes"]["en_cours"] == 1 and r_inf["total_prevu"] == 1
    assert client.get("/aujourdhui", headers=entete(client, "tec")).status_code == 403


def test_postes_indisponibles_et_patient_empeche(client):
    h, p, po = _prep(client)
    client.put(f"/postes/{po['id']}", json={"statut": "maintenance"}, headers=entete(client, "tec"))
    r = client.get("/aujourdhui", headers=h).json()
    assert r["postes_indisponibles"] == 1 and r["postes"][0]["etat"] == "maintenance"
    client.put(f"/postes/{po['id']}", json={"statut": "actif"}, headers=entete(client, "tec"))
    s = _seance(client, h, p, po, "soir")
    db.base().seances.update_one({"id": s["id"]}, {"$set": {"confirmation_wa": "empeche"}})
    assert client.get("/aujourdhui", headers=h).json()["empeches"][0]["patient"]["code"] == p["code"]


def test_aujourdhui_par_centre_et_pastille(client):
    b, hb = _centre_b(client)
    h, p, po = _prep(client)
    s = _seance(client, h, p, po)
    db.base().seances.update_one({"id": s["id"]}, {"$set": {"heure_prevue": "00:00"}})                  # heure déjà passée : en retard
    assert client.get("/aujourdhui", headers=hb).json()["total_prevu"] == 0                                # l'autre centre ne voit rien
    assert client.get("/notifications/compteurs", headers=h).json().get("/aujourdhui", 0) >= 1
