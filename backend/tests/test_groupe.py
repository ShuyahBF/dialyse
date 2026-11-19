"""Vue du groupe : synthèse de tous les centres (agrégée) et transfert d'un patient d'un centre à l'autre."""
from app import db, securite
from conftest import entete, nouveau_patient
from test_multi_centres import _centre_b


def _dg_groupe(client):
    """Directeur général « du groupe » : aucun centre."""
    db.brut().utilisateurs.insert_one({"id": "id-dgg", "login": "dgg", "nom_affiche": "dgg", "role": "direction", "actif": True, "echecs": 0, "centre_id": None,
                                       "mot_de_passe_hash": securite.hacher_mot_de_passe("Motdepasse1"), "doit_changer_mdp": False})
    r = client.post("/auth/login", json={"login": "dgg", "mot_de_passe": "Motdepasse1"})
    return {"Authorization": "Bearer " + r.json()["jeton"]}


def test_synthese_de_tous_les_centres(client):
    b, hb = _centre_b(client)
    hg = _dg_groupe(client)
    r = client.get("/groupe/synthese?du=2026-11-01&au=2026-11-30", headers=hg)          # sans centre choisi : la vue de groupe n'en a pas besoin
    assert r.status_code == 200, r.text
    d = r.json()
    assert {c["nom"] for c in d["centres"]} == {"Centre principal", "Clinique Pilote"}
    assert {"realisees", "patients_actifs", "facture", "encaisse", "taux_absence_pct"} <= set(d["total"])
    assert "nom" not in str(d["centres"][0].get("patients_liste", ""))                   # agrégé : aucune identité de patient
    # le contexte n'est pas « resté » sur un centre
    assert client.get("/rapports/activite?du=2026-11-01&au=2026-11-30", headers=hg).status_code == 400          # un rapport de centre exige un centre choisi


def test_synthese_reservee_au_groupe(client):
    b, hb = _centre_b(client)
    ha = entete(client, "adm")
    assert client.get("/groupe/synthese?du=2026-11-01&au=2026-11-30", headers=ha).status_code == 403
    db.brut().utilisateurs.update_one({"login": "adm"}, {"$set": {"role": "direction"}})                 # direction RATTACHÉE à un centre : pas la vue de groupe
    assert client.get("/groupe/synthese?du=2026-11-01&au=2026-11-30", headers=entete(client, "adm")).status_code == 403
    assert client.get("/groupe/synthese?du=2026-11-01&au=2026-11-30", headers=entete(client, "sa")).status_code == 200


def test_transfert_d_un_patient(client):
    b, hb = _centre_b(client)
    ha, hs = entete(client, "adm"), entete(client, "sa")
    p = nouveau_patient(client, ha)
    corps = {"centre_destination_id": b["id"], "motif": "Déménagement du patient", "consentement": True}
    assert client.post(f"/patients/{p['id']}/transfert", json={**corps, "consentement": False}, headers=hs).status_code == 422       # consentement obligatoire
    assert client.post(f"/patients/{p['id']}/transfert", json=corps, headers=ha).status_code == 403                                  # super administrateur seul
    r = client.post(f"/patients/{p['id']}/transfert", json=corps, headers=hs)
    assert r.status_code == 200, r.text
    assert r.json()["code_arrivee"] == "CMC-000001"
    # arrivée : le dossier est visible du centre B, pas de A ; départ : « Transféré »
    liste_b = client.get("/patients", headers=hb).json()
    assert len(liste_b) == 1 and liste_b[0]["code"] == "CMC-000001" and liste_b[0]["nom"] == p["nom"]
    assert client.get(f"/patients/{p['id']}", headers=ha).json()["statut"] == "transfere"
    # un patient déjà transféré ne se transfère pas deux fois, et un même centre est refusé
    assert client.post(f"/patients/{p['id']}/transfert", json=corps, headers=hs).status_code == 409
    q = nouveau_patient(client, ha, nom="Zongo")
    assert client.post(f"/patients/{q['id']}/transfert", json={**corps, "centre_destination_id": "centre-initial"}, headers=hs).status_code == 422
    # journalisé dans les DEUX centres
    assert [l for l in client.get("/journal", headers=ha).json() if l["action"] == "patient_transfere_depart"]
    assert [l for l in client.get("/journal", headers=hb).json() if l["action"] == "patient_transfere_arrivee"]
