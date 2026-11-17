"""Fixtures de test : base MongoDB en mémoire (mongomock), un compte par rôle."""
import os
import sys

import mongomock
import pytest
from fastapi.testclient import TestClient

os.environ["JWT_SECRET"] = "secret-de-test-assez-long-123456"
os.environ["PRESENCE_SAWALI"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import db, securite  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    base = mongomock.MongoClient()["test"]
    db.definir_base(base)
    db.creer_index(base)
    for login, role in [("sa", "super_admin"), ("adm", "admin"), ("med", "medecin"), ("inf", "infirmier"), ("sec", "secretariat"), ("tec", "technicien")]:
        base.utilisateurs.insert_one({"id": "id-" + login, "login": login, "nom_affiche": login, "role": role, "actif": True, "echecs": 0,
                                      "mot_de_passe_hash": securite.hacher_mot_de_passe("Motdepasse1"), "doit_changer_mdp": False})
    return TestClient(app)


def entete(client, login):
    """En-tête d'authentification pour le compte « login »."""
    r = client.post("/auth/login", json={"login": login, "mot_de_passe": "Motdepasse1"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["jeton"]}


def nouveau_patient(client, h, **extra):
    corps = {"nom": "Ouedraogo", "prenom": "Awa", "sexe": "F", "date_naissance": "1975-03-02", "telephone": "70000000", **extra}
    r = client.post("/patients", json=corps, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def nouveau_poste(client, h, nom="Poste 1", **extra):
    r = client.post("/postes", json={"nom": nom, **extra}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()
