"""Planning et déroulement des séances : conflits, isolement sérologique, cycle de vie, alertes, génération, confidentialité."""
from conftest import entete, nouveau_patient, nouveau_poste

JOUR = "2030-01-07"          # un lundi


def _prepare(client):
    hm, ha = entete(client, "med"), entete(client, "adm")
    p = nouveau_patient(client, hm, poids_sec=60)
    poste = nouveau_poste(client, ha)
    return hm, ha, p, poste


def test_planifier_et_conflits(client):
    hm, ha, p, poste = _prepare(client)
    s = client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hm)
    assert s.status_code == 200 and s.json()["statut"] == "planifiee" and s.json()["heure_prevue"] == "07:00"
    autre = nouveau_patient(client, hm, nom="Sawadogo", prenom="Issa")
    # même poste, même créneau
    assert client.post("/seances", json={"patient_id": autre["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hm).status_code == 409
    # même patient, même créneau, autre poste
    p2 = nouveau_poste(client, ha, "Poste 2")
    assert client.post("/seances", json={"patient_id": p["id"], "poste_id": p2["id"], "date": JOUR, "creneau": "matin"}, headers=hm).status_code == 409
    # autre créneau : accepté
    assert client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "soir"}, headers=hm).status_code == 200


def test_poste_hors_service_et_patient_inactif(client):
    hm, ha, p, poste = _prepare(client)
    client.put(f"/postes/{poste['id']}", json={"statut": "maintenance"}, headers=ha)
    assert client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hm).status_code == 409
    client.put(f"/postes/{poste['id']}", json={"statut": "actif"}, headers=ha)
    client.put(f"/patients/{p['id']}", json={"statut": "greffe"}, headers=hm)
    assert client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hm).status_code == 409


def test_alerte_isolement_serologique(client):
    hm, ha, _, poste = _prepare(client)
    pos = nouveau_patient(client, hm, nom="Kabore", prenom="Paul", serologies={"vhb": "positif", "vhc": "negatif", "vih": "negatif"})
    r = client.post("/seances", json={"patient_id": pos["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hm).json()
    assert any("isolement" in a for a in r["alertes_planification"])
    iso = nouveau_poste(client, ha, "Poste isolé", isolement=True)
    r = client.post("/seances", json={"patient_id": pos["id"], "poste_id": iso["id"], "date": JOUR, "creneau": "midi"}, headers=hm).json()
    assert r["alertes_planification"] == []


def test_cycle_complet_et_validation(client):
    hm, ha, p, poste = _prepare(client)
    hi = entete(client, "inf")
    client.put(f"/patients/{p['id']}", json={"prescription": {"duree_min": 240, "debit_sang": 300, "dialyseur": "FX60"}}, headers=hm)
    s = client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hm).json()
    sid = s["id"]
    # impossible de surveiller ou terminer avant le démarrage
    assert client.post(f"/seances/{sid}/surveillance", json={"tension_sys": 120}, headers=hi).status_code == 409
    assert client.post(f"/seances/{sid}/terminer", json={"post": {"poids": 60}}, headers=hi).status_code == 409
    # démarrage : poids et tension obligatoires
    assert client.post(f"/seances/{sid}/demarrer", json={"pre": {"poids": 63}}, headers=hi).status_code == 422
    d = client.post(f"/seances/{sid}/demarrer", json={"pre": {"poids": 65, "tension_sys": 150, "tension_dia": 90}}, headers=hi).json()
    assert d["statut"] == "en_cours" and d["parametres"]["debit_sang"] == 300 and d["parametres"]["dialyseur"] == "FX60"   # repris de la prescription
    assert any("Prise de poids" in a["message"] for a in d["alertes"])                  # 65 kg pour un poids sec de 60 kg
    r = client.post(f"/seances/{sid}/surveillance", json={"heure": "08:00", "tension_sys": 85, "tension_dia": 50}, headers=hi).json()
    assert any("Hypotension pendant" in a["message"] for a in r["alertes"])
    client.post(f"/seances/{sid}/incident", json={"type": "Crampes", "conduite": "Réduction de l'UF"}, headers=hi)
    assert client.post(f"/seances/{sid}/incident", json={"type": "Inconnu"}, headers=hi).status_code == 422
    t = client.post(f"/seances/{sid}/terminer", json={"post": {"poids": 61.5, "tension_sys": 120, "tension_dia": 70, "volume_uf_l": 3.5, "kt_v": 1.0, "duree_reelle_min": 200}}, headers=hi).json()
    assert t["statut"] == "terminee"
    msgs = " ".join(a["message"] for a in t["alertes"])
    assert "Kt/V" in msgs and "écourtée" in msgs and "incident" in msgs
    # validation : médecin seulement, puis verrouillage
    assert client.post(f"/seances/{sid}/valider", json={}, headers=hi).status_code == 403
    v = client.post(f"/seances/{sid}/valider", json={"avis": "RAS"}, headers=hm).json()
    assert v["validee_par"] == "med"
    assert client.post(f"/seances/{sid}/valider", json={}, headers=hm).status_code == 409
    assert client.post(f"/seances/{sid}/annuler", json={"motif": "x"}, headers=hm).status_code == 409


def test_constantes_invraisemblables_refusees(client):
    hm, ha, p, poste = _prepare(client)
    hi = entete(client, "inf")
    sid = client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hm).json()["id"]
    assert client.post(f"/seances/{sid}/demarrer", json={"pre": {"poids": 600, "tension_sys": 120, "tension_dia": 80}}, headers=hi).status_code == 422
    assert client.post(f"/seances/{sid}/demarrer", json={"pre": {"poids": 60, "tension_sys": 80, "tension_dia": 120}}, headers=hi).status_code == 422


def test_poste_en_cours_ne_passe_pas_en_maintenance(client):
    hm, ha, p, poste = _prepare(client)
    hi = entete(client, "inf")
    sid = client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hm).json()["id"]
    client.post(f"/seances/{sid}/demarrer", json={"pre": {"poids": 60, "tension_sys": 120, "tension_dia": 80}}, headers=hi)
    assert client.put(f"/postes/{poste['id']}", json={"statut": "hors_service"}, headers=ha).status_code == 409


def test_annulation_absence_et_deplacement(client):
    hm, ha, p, poste = _prepare(client)
    hs = entete(client, "sec")
    sid = client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hs).json()["id"]
    d = client.put(f"/seances/{sid}", json={"creneau": "soir"}, headers=hs).json()
    assert d["creneau"] == "soir"
    assert client.post(f"/seances/{sid}/annuler", json={}, headers=hs).status_code == 422          # motif obligatoire
    a = client.post(f"/seances/{sid}/annuler", json={"absent": True}, headers=hs).json()
    assert a["statut"] == "absente"
    # le créneau est libéré : on peut replanifier le même patient
    assert client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "soir"}, headers=hs).status_code == 200


def test_secretariat_voit_le_planning_sans_le_medical(client):
    hm, ha, p, poste = _prepare(client)
    hi, hs = entete(client, "inf"), entete(client, "sec")
    sid = client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": JOUR, "creneau": "matin"}, headers=hm).json()["id"]
    client.post(f"/seances/{sid}/demarrer", json={"pre": {"poids": 60, "tension_sys": 120, "tension_dia": 80}}, headers=hi)
    s = client.get(f"/seances?date_={JOUR}", headers=hs).json()[0]
    assert s["patient"]["nom"] == "OUEDRAOGO" and s["poste_nom"] == "Poste 1" and s["statut"] == "en_cours"
    for k in ("pre", "post", "parametres", "alertes", "surveillance", "incidents", "serologie_positive"):
        assert k not in s
    assert "pre" not in client.get(f"/seances/{sid}", headers=hs).json()
    # le secrétariat ne peut ni démarrer ni valider
    assert client.post(f"/seances/{sid}/surveillance", json={}, headers=hs).status_code == 403


def test_generation_du_planning(client):
    hm, ha = entete(client, "med"), entete(client, "adm")
    presc = {"prescription": {"duree_min": 240, "frequence_semaine": 3, "jours": ["lundi", "mercredi", "vendredi"], "creneau": "matin"}}
    p1 = nouveau_patient(client, hm)
    p2 = nouveau_patient(client, hm, nom="Kabore", prenom="Paul", serologies={"vhb": "positif", "vhc": "negatif", "vih": "negatif"})
    for p in (p1, p2):
        client.put(f"/patients/{p['id']}", json=presc, headers=hm)
    nouveau_poste(client, ha, "Poste 1")
    # semaine du lundi 7 au dimanche 13 janvier 2030 : 3 jours × 2 patients = 6 séances ; le patient positif n'a pas de poste d'isolement
    r = client.post("/seances/generer", json={"du": "2030-01-07", "au": "2030-01-13"}, headers=hm).json()
    assert r["creees"] == 3 and len(r["non_placees"]) == 3
    assert all("isolement" in x["raison"] for x in r["non_placees"])
    nouveau_poste(client, ha, "Isolé", isolement=True)
    r = client.post("/seances/generer", json={"du": "2030-01-07", "au": "2030-01-13"}, headers=hm).json()
    assert r["creees"] == 3 and r["non_placees"] == [] and r["deja_existantes"] == 3          # idempotent
    liste = client.get("/seances?du=2030-01-07&au=2030-01-13", headers=hm).json()
    assert len(liste) == 6
    for s in liste:
        assert s["poste_isolement"] == (s["patient"]["nom"] == "KABORE")
    assert client.post("/seances/generer", json={"du": "2030-01-07", "au": "2030-04-13"}, headers=hm).status_code == 422


def test_tableau_de_bord(client):
    hm, ha, p, poste = _prepare(client)
    from datetime import date
    client.post("/seances", json={"patient_id": p["id"], "poste_id": poste["id"], "date": date.today().isoformat(), "creneau": "matin"}, headers=hm)
    t = client.get("/tableau", headers=hm).json()
    assert t["seances_jour"]["total"] == 1 and t["patients_actifs"] == 1 and t["postes"]["en_service"] == 1 and t["occupation_pct"] == 33
    assert len(t["seances_par_mois"]) == 6
    assert client.get("/tableau", headers=entete(client, "sec")).status_code == 403
