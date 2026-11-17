"""Postes (machines) et gestion des comptes."""
from conftest import entete, nouveau_patient, nouveau_poste


def test_postes_droits_et_unicite(client):
    ht, hs = entete(client, "tec"), entete(client, "sec")
    p = nouveau_poste(client, ht)
    assert client.post("/postes", json={"nom": "Poste 1"}, headers=ht).status_code == 409
    assert client.post("/postes", json={"nom": "Poste X"}, headers=hs).status_code == 403
    assert client.get("/postes", headers=hs).status_code == 200            # tous peuvent voir les postes
    m = client.post(f"/postes/{p['id']}/maintenance", json={"date": "2026-03-01", "type": "Préventive", "prochaine": "2026-09-01"}, headers=ht).json()
    assert m["type"] == "Préventive"
    fiche = [x for x in client.get("/postes", headers=ht).json() if x["id"] == p["id"]][0]
    assert fiche["derniere_maintenance"] == "2026-03-01" and fiche["prochaine_maintenance"] == "2026-09-01"


def test_suppression_poste_avec_seances_refusee(client):
    hm, ha = entete(client, "med"), entete(client, "adm")
    pat, poste = nouveau_patient(client, hm), nouveau_poste(client, ha)
    client.post("/seances", json={"patient_id": pat["id"], "poste_id": poste["id"], "date": "2030-01-07", "creneau": "matin"}, headers=hm)
    assert client.delete(f"/postes/{poste['id']}", headers=ha).status_code == 409


def test_admin_cree_des_comptes_limites(client):
    ha = entete(client, "adm")
    r = client.post("/utilisateurs", json={"login": "Awa.K", "nom_affiche": "Awa K.", "role": "infirmier", "mot_de_passe": "Provisoire1"}, headers=ha)
    assert r.status_code == 200 and r.json()["login"] == "awa.k" and r.json()["doit_changer_mdp"] is True
    assert "mot_de_passe_hash" not in r.json()
    # un admin ne crée ni admin ni super admin
    assert client.post("/utilisateurs", json={"login": "x1", "nom_affiche": "X", "role": "admin", "mot_de_passe": "Provisoire1"}, headers=ha).status_code == 403
    assert client.post("/utilisateurs", json={"login": "awa.k", "nom_affiche": "X", "role": "infirmier", "mot_de_passe": "Provisoire1"}, headers=ha).status_code == 409
    assert client.post("/utilisateurs", json={"login": "x2", "nom_affiche": "X", "role": "infirmier", "mot_de_passe": "faible"}, headers=ha).status_code == 422
    # le super administrateur peut créer un admin
    hs = entete(client, "sa")
    assert client.post("/utilisateurs", json={"login": "adm2", "nom_affiche": "Adm 2", "role": "admin", "mot_de_passe": "Provisoire1"}, headers=hs).status_code == 200
    assert [r["valeur"] for r in client.get("/roles", headers=ha).json()] == ["direction", "medecin", "infirmier", "secretariat", "technicien"]


def test_gestion_des_comptes(client):
    ha, hm = entete(client, "adm"), entete(client, "med")
    comptes = client.get("/utilisateurs", headers=ha).json()
    inf = next(c for c in comptes if c["login"] == "inf")
    admin = next(c for c in comptes if c["login"] == "adm")
    assert client.get("/utilisateurs", headers=hm).status_code == 403
    assert client.put(f"/utilisateurs/{admin['id']}", json={"actif": False}, headers=ha).status_code == 400        # pas son propre compte
    sa = next(c for c in comptes if c["login"] == "sa")
    assert client.put(f"/utilisateurs/{sa['id']}", json={"actif": False}, headers=ha).status_code == 403            # pas le super administrateur
    client.put(f"/utilisateurs/{inf['id']}", json={"actif": False}, headers=ha)
    assert client.post("/auth/login", json={"login": "inf", "mot_de_passe": "Motdepasse1"}).status_code == 401      # compte désactivé
    client.post(f"/utilisateurs/{inf['id']}/reinitialiser", json={"mot_de_passe": "Nouveau1234"}, headers=ha)
    client.put(f"/utilisateurs/{inf['id']}", json={"actif": True}, headers=ha)
    r = client.post("/auth/login", json={"login": "inf", "mot_de_passe": "Nouveau1234"}).json()
    assert r["doit_changer_mdp"] is True


def test_changer_mot_de_passe(client):
    hi = entete(client, "inf")
    assert client.post("/auth/changer-mot-de-passe", json={"ancien": "faux", "nouveau": "Autrepass12"}, headers=hi).status_code == 400
    assert client.post("/auth/changer-mot-de-passe", json={"ancien": "Motdepasse1", "nouveau": "court"}, headers=hi).status_code == 400
    assert client.post("/auth/changer-mot-de-passe", json={"ancien": "Motdepasse1", "nouveau": "Autrepass12"}, headers=hi).status_code == 200
    assert client.post("/auth/login", json={"login": "inf", "mot_de_passe": "Autrepass12"}).status_code == 200


def test_double_authentification(client):
    from app import deuxfacteurs as t
    hi = entete(client, "inf")
    prep = client.post("/auth/2fa/preparer", headers=hi).json()
    code = t.code_a(prep["secret"], __import__("time").time())
    assert client.post("/auth/2fa/activer", json={"code": code}, headers=hi).status_code == 200
    r = client.post("/auth/login", json={"login": "inf", "mot_de_passe": "Motdepasse1"})
    assert r.status_code == 401 and r.json()["detail"] == "CODE_2FA_REQUIS"


def test_version_et_sante(client):
    v = client.get("/api/version").json()
    assert v["version"] and v["lot"] and v["deploye_le"]
    assert client.get("/api/sante").json()["serveur"] == "actif"
