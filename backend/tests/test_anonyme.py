"""Suivi anonymisé (DG, médecins) : aucune identité, alertes stables, jeton de lecture pour les notifications du téléphone."""
import json
from datetime import date, timedelta

from app import db, securite
from conftest import entete, nouveau_patient


def _dg(client):
    db.base().utilisateurs.insert_one({"id": "id-dg", "login": "dg", "nom_affiche": "dg", "role": "direction", "actif": True, "echecs": 0,
                                       "mot_de_passe_hash": securite.hacher_mot_de_passe("Motdepasse1"), "doit_changer_mdp": False})
    return entete(client, "dg")


def _preparer(client):
    hm, hi = entete(client, "med"), entete(client, "inf")
    p = nouveau_patient(client, hm, nom="Zongo", prenom="Fatimata", telephone="76123456")
    hier = (date.today() - timedelta(days=1)).isoformat()
    # Bilan critique (potassium) pour ce patient
    r = client.post(f"/patients/{p['id']}/bilans", json={"date_prelevement": hier, "type": "Mensuel", "resultats": {"potassium": 6.5}}, headers=hi)
    assert r.status_code == 200, r.text
    return p


def test_aucune_identite_et_alertes(client):
    p = _preparer(client)
    h = _dg(client)
    r = client.get("/anonyme", headers=h)
    assert r.status_code == 200
    brut = json.dumps(r.json())
    for interdit in ("Zongo", "Fatimata", "76123456", p["nom"]):
        assert interdit not in brut                                   # le masquage est fait par le serveur
    d = r.json()
    assert d["critiques"] >= 1 and any(a["type"] == "bilan_critique" and a["code"] == p["code"] for a in d["alertes"])
    ligne = next(x for x in d["patients"] if x["code"] == p["code"])
    assert set(ligne) == {"code", "age", "sexe", "statut", "alertes_critiques", "alertes_attention", "dernier_bilan"} and ligne["alertes_critiques"] >= 1
    assert d == client.get("/anonyme", headers=h).json()              # identifiants stables d'un appel à l'autre


def test_droits(client):
    h_sec, h_inf = entete(client, "sec"), entete(client, "inf")
    assert client.get("/anonyme", headers=h_sec).status_code == 403
    assert client.get("/anonyme", headers=h_inf).status_code == 403
    assert client.get("/anonyme", headers=entete(client, "med")).status_code == 200
    assert client.get("/anonyme").status_code == 401


def test_jeton_notifications(client):
    _preparer(client)
    h = _dg(client)
    assert client.get("/anonyme/flux").status_code == 401
    jeton = client.post("/anonyme/jeton", json={"appareil": "Pixel"}, headers=h).json()["jeton"]
    f = client.get("/anonyme/flux", headers={"X-Jeton-Alertes": jeton})
    assert f.status_code == 200 and f.json()["critiques"] >= 1
    assert client.get("/anonyme/flux", headers={"X-Jeton-Alertes": "x" * 40}).status_code == 401
    # le jeton ne donne accès à rien d'autre
    assert client.get("/patients", headers={"X-Jeton-Alertes": jeton}).status_code == 401
    # compte désactivé : jeton refusé ; retrait : jeton refusé
    db.base().utilisateurs.update_one({"login": "dg"}, {"$set": {"actif": False}})
    assert client.get("/anonyme/flux", headers={"X-Jeton-Alertes": jeton}).status_code == 401
    db.base().utilisateurs.update_one({"login": "dg"}, {"$set": {"actif": True}})
    assert client.get("/anonyme/flux", headers={"X-Jeton-Alertes": jeton}).status_code == 200
    assert client.delete("/anonyme/jeton", headers=h).json()["retires"] == 1
    assert client.get("/anonyme/flux", headers={"X-Jeton-Alertes": jeton}).status_code == 401
