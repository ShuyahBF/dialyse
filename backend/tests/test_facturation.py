"""Facturation : répartition organisme / patient, factures par séance, paiements, annulation, synthèse, PDF, droits."""
from app import facturation as fa
from conftest import entete, nouveau_patient, nouveau_poste


def test_calculs_purs():
    assert fa.repartir(45000, 80) == (36000, 9000)
    assert fa.repartir(10001, 33) == (3300, 6701)              # la part patient est le complément : jamais de dérive d'arrondi
    assert fa.repartir(100, 150) == (100, 0) and fa.repartir(100, -5) == (0, 100) and fa.repartir(100, None) == (0, 100)
    f = {"total": 1000, "part_patient": 200, "part_organisme": 800, "paiements": []}
    assert fa.statut_facture(f) == "emise"
    f["paiements"] = [{"payeur": "patient", "montant": 200}]
    assert fa.statut_facture(f) == "partielle" and fa.soldes(f)["reste_patient"] == 0 and fa.soldes(f)["reste_organisme"] == 800
    f["paiements"].append({"payeur": "organisme", "montant": 800})
    assert fa.statut_facture(f) == "payee"
    assert fa.statut_facture({**f, "annulee": True}) == "annulee"
    assert fa.fcfa(1234567) == "1 234 567 FCFA"


def _decor(client, taux_org=80):
    """Un patient pris en charge par une assurance, un tarif de séance automatique, une séance terminée. Renvoie (headers, patient, séance, organisme)."""
    ha, hm, hi, hs = entete(client, "adm"), entete(client, "med"), entete(client, "inf"), entete(client, "sec")
    org = client.post("/facturation/organismes", json={"nom": "CNSS", "type": "Assurance maladie", "taux": taux_org}, headers=ha).json()
    client.post("/facturation/tarifs", json={"libelle": "Séance d'hémodialyse", "prix": 45000, "automatique": True}, headers=ha)
    pat = nouveau_patient(client, hm)
    assert client.put(f"/patients/{pat['id']}", json={"organisme_id": org["id"], "numero_assurance": "A-123"}, headers=hs).status_code == 200
    poste = nouveau_poste(client, ha)
    sid = client.post("/seances", json={"patient_id": pat["id"], "poste_id": poste["id"], "date": "2030-01-07", "creneau": "matin"}, headers=hm).json()["id"]
    return ha, hm, hi, hs, pat, sid, org


def _terminer(client, hi, sid):
    client.post(f"/seances/{sid}/demarrer", json={"pre": {"poids": 60, "tension_sys": 120, "tension_dia": 80}}, headers=hi)
    client.post(f"/seances/{sid}/terminer", json={"post": {"poids": 58}}, headers=hi)


def test_droits_parametrage(client):
    ha, hs, hm = entete(client, "adm"), entete(client, "sec"), entete(client, "med")
    assert client.post("/facturation/tarifs", json={"libelle": "X", "prix": 100}, headers=hs).status_code == 403          # le secrétariat ne fixe pas les prix
    assert client.post("/facturation/tarifs", json={"libelle": "X", "prix": 100.5}, headers=ha).status_code == 422      # FCFA entier
    assert client.post("/facturation/tarifs", json={"libelle": "X", "prix": 100}, headers=ha).status_code == 200
    assert client.post("/facturation/tarifs", json={"libelle": "X", "prix": 100}, headers=ha).status_code == 409
    assert client.get("/facturation/tarifs", headers=hs).status_code == 200
    assert client.get("/facturation/tarifs", headers=hm).status_code == 403                                                # le médecin n'a pas accès à la caisse
    assert client.post("/facturation/organismes", json={"nom": "Y", "type": "Inconnu"}, headers=ha).status_code == 422
    assert client.put("/patients/x", json={"organisme_id": "inexistant"}, headers=hs).status_code in (404, 422)


def test_facturer_une_seance(client):
    ha, hm, hi, hs, pat, sid, org = _decor(client)
    assert client.post(f"/factures/seance/{sid}", headers=hs).status_code == 409          # séance non terminée
    _terminer(client, hi, sid)
    f = client.post(f"/factures/seance/{sid}", headers=hs).json()
    assert f["numero"].startswith("FAC-") and f["numero"].endswith("-000001")
    assert (f["total"], f["part_organisme"], f["part_patient"], f["taux"]) == (45000, 36000, 9000, 80)
    assert f["organisme_nom"] == "CNSS" and f["patient_code"] == pat["code"] and f["statut"] == "emise" and f["reste"] == 45000
    assert client.post(f"/factures/seance/{sid}", headers=hs).status_code == 409           # une seule facture par séance
    # une modification de tarif ne change pas une facture émise
    tid = client.get("/facturation/tarifs", headers=hs).json()[0]["id"]
    client.put(f"/facturation/tarifs/{tid}", json={"prix": 99999}, headers=ha)
    assert client.get(f"/factures/{f['id']}", headers=hs).json()["total"] == 45000


def test_taux_personnalise_et_paiement_direct(client):
    ha, hm, hi, hs, pat, sid, org = _decor(client)
    client.put(f"/patients/{pat['id']}", json={"taux_prise_en_charge": 50}, headers=hs)
    _terminer(client, hi, sid)
    f = client.post(f"/factures/seance/{sid}", headers=hs).json()
    assert (f["part_organisme"], f["part_patient"]) == (22500, 22500)                     # le taux du patient prime sur celui de l'organisme
    autre = nouveau_patient(client, hm, nom="Sawadogo", prenom="Issa")                     # sans organisme : paiement direct
    poste = nouveau_poste(client, ha, "Poste 2")
    s2 = client.post("/seances", json={"patient_id": autre["id"], "poste_id": poste["id"], "date": "2030-01-07", "creneau": "midi"}, headers=hm).json()["id"]
    _terminer(client, hi, s2)
    g = client.post(f"/factures/seance/{s2}", headers=hs).json()
    assert (g["part_organisme"], g["part_patient"], g["organisme_nom"]) == (0, 45000, "")
    assert client.post(f"/factures/{g['id']}/paiements", json={"payeur": "organisme", "montant": 1, "mode": "Espèces"}, headers=hs).status_code == 409


def test_paiements_partiels_et_plafonds(client):
    ha, hm, hi, hs, pat, sid, org = _decor(client)
    _terminer(client, hi, sid)
    f = client.post(f"/factures/seance/{sid}", headers=hs).json()
    pay = lambda payeur, m, mode="Espèces": client.post(f"/factures/{f['id']}/paiements", json={"payeur": payeur, "montant": m, "mode": mode}, headers=hs)
    assert pay("patient", 10000).status_code == 409                    # la part patient n'est que de 9 000
    assert pay("patient", 0).status_code == 422 and pay("patient", 5000, "Troc").status_code == 422
    r = pay("patient", 5000, "Orange Money").json()
    assert r["statut"] == "partielle" and r["reste_patient"] == 4000 and r["reste"] == 40000
    assert pay("patient", 4000).json()["reste_patient"] == 0
    r = pay("organisme", 36000, "Virement bancaire").json()
    assert r["statut"] == "payee" and r["reste"] == 0
    assert pay("organisme", 1).status_code == 409
    # une facture payée ne s'annule pas
    assert client.post(f"/factures/{f['id']}/annuler", json={"motif": "erreur"}, headers=ha).status_code == 409


def test_annulation_et_refacturation(client):
    ha, hm, hi, hs, pat, sid, org = _decor(client)
    _terminer(client, hi, sid)
    f = client.post(f"/factures/seance/{sid}", headers=hs).json()
    assert client.post(f"/factures/{f['id']}/annuler", json={"motif": "x"}, headers=hs).status_code == 403            # administration seulement
    assert client.post(f"/factures/{f['id']}/annuler", json={}, headers=ha).status_code == 422                          # motif obligatoire
    a = client.post(f"/factures/{f['id']}/annuler", json={"motif": "Erreur de tarif"}, headers=ha).json()
    assert a["statut"] == "annulee" and a["reste"] == 0
    assert client.post(f"/factures/{f['id']}/paiements", json={"payeur": "patient", "montant": 1, "mode": "Espèces"}, headers=hs).status_code == 409
    nouvelle = client.post(f"/factures/seance/{sid}", headers=hs).json()                    # la séance peut être refacturée
    assert nouvelle["numero"].endswith("-000002")


def test_generation_en_bloc(client):
    ha, hm, hi, hs, pat, sid, org = _decor(client)
    _terminer(client, hi, sid)
    poste = nouveau_poste(client, ha, "Poste 2")
    s2 = client.post("/seances", json={"patient_id": pat["id"], "poste_id": poste["id"], "date": "2030-01-09", "creneau": "matin"}, headers=hm).json()["id"]   # non terminée
    r = client.post("/factures/generer", json={"du": "2030-01-01", "au": "2030-01-31"}, headers=hs).json()
    assert r == {"creees": 1, "deja_facturees": 0}
    assert client.post("/factures/generer", json={"du": "2030-01-01", "au": "2030-01-31"}, headers=hs).json() == {"creees": 0, "deja_facturees": 1}
    assert client.post("/factures/generer", json={"du": "2030-02-01", "au": "2030-01-01"}, headers=hs).status_code == 422


def test_sans_tarif_automatique(client):
    ha, hm, hi, hs = entete(client, "adm"), entete(client, "med"), entete(client, "inf"), entete(client, "sec")
    pat = nouveau_patient(client, hm)
    poste = nouveau_poste(client, ha)
    sid = client.post("/seances", json={"patient_id": pat["id"], "poste_id": poste["id"], "date": "2030-01-07", "creneau": "matin"}, headers=hm).json()["id"]
    _terminer(client, hi, sid)
    r = client.post(f"/factures/seance/{sid}", headers=hs)
    assert r.status_code == 409 and "tarif" in r.json()["detail"].lower()


def test_synthese_et_filtres(client):
    ha, hm, hi, hs, pat, sid, org = _decor(client)
    _terminer(client, hi, sid)
    f = client.post(f"/factures/seance/{sid}", headers=hs).json()
    client.post(f"/factures/{f['id']}/paiements", json={"payeur": "patient", "montant": 9000, "mode": "Espèces"}, headers=hs)
    s = client.get("/facturation/synthese?du=2030-01-01&au=2030-01-31", headers=hs).json()
    assert (s["facture"], s["encaisse_patients"], s["encaisse_organismes"], s["reste"]) == (45000, 9000, 0, 36000)
    assert s["creances_organismes"] == [{"organisme": "CNSS", "factures": 1, "reste": 36000}] and s["impayes_patients"] == []
    assert len(client.get(f"/factures?statut=partielle&organisme_id={org['id']}", headers=hs).json()) == 1
    assert client.get("/factures?statut=payee", headers=hs).json() == []
    assert client.get("/factures?patient_id=zzz", headers=hs).json() == []


def test_pdf_et_clinique(client):
    ha, hm, hi, hs, pat, sid, org = _decor(client)
    _terminer(client, hi, sid)
    f = client.post(f"/factures/seance/{sid}", headers=hs).json()
    assert client.put("/facturation/clinique", json={"nom": "Clinique Philadelphie", "adresse": "Ouagadougou"}, headers=hs).status_code == 403
    client.put("/facturation/clinique", json={"nom": "Clinique Philadelphie", "adresse": "Ouagadougou", "telephone": "25 00 00 00"}, headers=ha)
    r = client.get(f"/factures/{f['id']}/pdf", headers=hs)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"
    assert "inline" in r.headers["content-disposition"] and "attachment" not in r.headers["content-disposition"]
    assert client.get(f"/factures/{f['id']}/pdf", headers=hm).status_code == 403
