"""Droits et confidentialité : le secrétariat ne voit jamais le médical ; chaque rôle n'écrit que ce qui lui revient."""
from conftest import entete, nouveau_patient


def test_connexion_et_blocage(client):
    for _ in range(5):
        assert client.post("/auth/login", json={"login": "med", "mot_de_passe": "faux"}).status_code == 401
    assert client.post("/auth/login", json={"login": "med", "mot_de_passe": "Motdepasse1"}).status_code == 429     # compte bloqué


def test_secretariat_ne_voit_pas_le_medical(client):
    hm, hs = entete(client, "med"), entete(client, "sec")
    p = nouveau_patient(client, hm, serologies={"vhb": "positif", "vhc": "negatif", "vih": "negatif"}, allergies="Pénicilline", poids_sec=60)
    vu_par_med = client.get(f"/patients/{p['id']}", headers=hm).json()
    assert vu_par_med["serologies"]["vhb"] == "positif" and vu_par_med["allergies"] == "Pénicilline"
    vu_par_sec = client.get(f"/patients/{p['id']}", headers=hs).json()
    assert vu_par_sec["nom"] == "OUEDRAOGO"
    for champ in ("serologies", "allergies", "poids_sec", "antecedents", "prescription", "acces_vasculaires"):
        assert champ not in vu_par_sec
    liste = client.get("/patients", headers=hs).json()
    assert "serologie_positive" not in liste[0] and "poids_sec" not in liste[0]


def test_technicien_sans_acces_aux_patients(client):
    assert client.get("/patients", headers=entete(client, "tec")).status_code == 403


def test_secretariat_ne_modifie_pas_le_medical(client):
    hm, hs = entete(client, "med"), entete(client, "sec")
    p = nouveau_patient(client, hm)
    assert client.put(f"/patients/{p['id']}", json={"telephone": "71111111"}, headers=hs).status_code == 200
    assert client.put(f"/patients/{p['id']}", json={"allergies": "x"}, headers=hs).status_code == 403
    assert client.put(f"/patients/{p['id']}", json={"statut": "decede"}, headers=hs).status_code == 403
    assert client.post(f"/patients/{p['id']}/acces", json={"type": "Cathéter temporaire", "localisation": "jugulaire"}, headers=hs).status_code == 403


def test_prescription_reservee_au_medecin(client):
    hm, hi = entete(client, "med"), entete(client, "inf")
    p = nouveau_patient(client, hm)
    presc = {"prescription": {"duree_min": 240, "frequence_semaine": 3, "jours": ["lundi", "mercredi", "vendredi"], "creneau": "matin", "debit_sang": 300}}
    assert client.put(f"/patients/{p['id']}", json=presc, headers=hi).status_code == 403
    r = client.put(f"/patients/{p['id']}", json=presc, headers=hm)
    assert r.status_code == 200 and r.json()["prescription"]["duree_min"] == 240


def test_prescription_incoherente_refusee(client):
    hm = entete(client, "med")
    p = nouveau_patient(client, hm)
    r = client.put(f"/patients/{p['id']}", json={"prescription": {"frequence_semaine": 3, "jours": ["lundi"]}}, headers=hm)
    assert r.status_code == 422
    r = client.put(f"/patients/{p['id']}", json={"prescription": {"duree_min": 5}}, headers=hm)
    assert r.status_code == 422


def test_doublon_et_code(client):
    hm = entete(client, "med")
    p1 = nouveau_patient(client, hm)
    assert p1["code"] == "DIAL-000001"
    r = client.post("/patients", json={"nom": "ouedraogo", "prenom": "AWA", "sexe": "F", "date_naissance": "1975-03-02"}, headers=hm)
    assert r.status_code == 409 and "DOUBLON" in r.json()["detail"]
    r = client.post("/patients", json={"nom": "ouedraogo", "prenom": "AWA", "sexe": "F", "date_naissance": "1975-03-02", "forcer": True}, headers=hm)
    assert r.status_code == 200 and r.json()["code"] == "DIAL-000002"


def test_ouverture_dossier_journalisee(client):
    hm, ha = entete(client, "med"), entete(client, "adm")
    p = nouveau_patient(client, hm)
    client.get(f"/patients/{p['id']}", headers=hm)
    lignes = client.get("/journal?action=patient_lu", headers=ha).json()
    assert lignes and lignes[0]["acteur"] == "med" and lignes[0]["detail"] == p["code"]
    assert client.get("/journal", headers=hm).status_code == 403          # le journal est réservé à l'administration


def test_historique_sans_valeurs(client):
    hm, ha = entete(client, "med"), entete(client, "adm")
    p = nouveau_patient(client, hm)
    client.put(f"/patients/{p['id']}", json={"allergies": "secret médical"}, headers=hm)
    h = client.get(f"/historique/patients/{p['id']}", headers=ha).json()
    assert any("allergies" in ligne["champs"] for ligne in h["lignes"])
    assert "secret médical" not in str(h)


def test_acces_vasculaire(client):
    hm = entete(client, "med")
    p = nouveau_patient(client, hm)
    a = client.post(f"/patients/{p['id']}/acces", json={"type": "Fistule artério-veineuse (FAV)", "localisation": "avant-bras gauche", "date_pose": "2025-01-10"}, headers=hm).json()
    assert client.post(f"/patients/{p['id']}/acces", json={"type": "inconnu", "localisation": "x"}, headers=hm).status_code == 422
    r = client.put(f"/patients/{p['id']}/acces/{a['id']}", json={"actif": False, "date_retrait": "2026-02-01"}, headers=hm).json()
    assert r["actif"] is False and r["date_retrait"] == "2026-02-01"


def test_suppression_patient(client):
    hm, ha = entete(client, "med"), entete(client, "adm")
    p = nouveau_patient(client, hm)
    assert client.delete(f"/patients/{p['id']}", headers=hm).status_code == 403
    assert client.delete(f"/patients/{p['id']}", headers=ha).status_code == 200
