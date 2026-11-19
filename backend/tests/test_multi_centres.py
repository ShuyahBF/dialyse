"""Multi-centres (modèle e-Kol) : chaque centre a ses patients, postes, stocks, comptes et journal ; aucun passage d'un centre à l'autre."""
from app import db, securite
from app.centres import CENTRE_INITIAL, amorcer_centre_initial
from conftest import CENTRE, entete, nouveau_patient, nouveau_poste


def _centre_b(client):
    """Le super administrateur crée le centre B (préfixe CMC) et son administrateur « admb »."""
    hs = entete(client, "sa")
    r = client.post("/centres", json={"nom": "Clinique Pilote", "prefixe": "cmc", "ville": "Bobo-Dioulasso"}, headers=hs)
    assert r.status_code == 200, r.text
    b = r.json()
    r = client.post("/utilisateurs", json={"login": "admb", "nom_affiche": "BADINI Awa", "role": "admin", "mot_de_passe": "Provisoire1", "centre_id": b["id"]}, headers=hs)
    assert r.status_code == 200, r.text
    db.brut().utilisateurs.update_one({"login": "admb"}, {"$set": {"doit_changer_mdp": False, "mot_de_passe_hash": securite.hacher_mot_de_passe("Motdepasse1")}})
    return b, entete(client, "admb")


def test_un_centre_ne_voit_pas_les_donnees_de_l_autre(client):
    b, hb = _centre_b(client)
    ha = entete(client, "adm")
    pa = nouveau_patient(client, ha)
    pb = nouveau_patient(client, hb, nom="Zongo")
    assert pa["code"].startswith("DIAL-") and pb["code"] == "CMC-000001"                     # un préfixe et un compteur par centre
    assert [p["id"] for p in client.get("/patients", headers=ha).json()] == [pa["id"]]
    assert [p["id"] for p in client.get("/patients", headers=hb).json()] == [pb["id"]]
    assert client.get(f"/patients/{pb['id']}", headers=ha).status_code == 404                # un identifiant d'un autre centre est « introuvable »
    assert client.put(f"/patients/{pa['id']}", json={"telephone": "1"}, headers=hb).status_code == 404
    nouveau_poste(client, ha, "Poste A")
    assert client.get("/postes", headers=hb).json() == []


def test_meme_nom_d_article_dans_deux_centres(client):
    b, hb = _centre_b(client)
    ha = entete(client, "adm")
    corps = {"nom": "Dialyseur FX60", "categorie": "Dialyseur", "unite": "pièce", "seuil_alerte": 5, "par_seance": 1}
    assert client.post("/stock/articles", json=corps, headers=ha).status_code == 200
    assert client.post("/stock/articles", json=corps, headers=hb).status_code == 200          # le nom n'est unique que DANS un centre
    assert client.post("/stock/articles", json=corps, headers=hb).status_code in (400, 409)


def test_comptes_cloisonnes_et_en_tete_ignore(client):
    b, hb = _centre_b(client)
    ha = entete(client, "adm")
    assert {c["login"] for c in client.get("/utilisateurs", headers=ha).json()} == {"adm", "med", "inf", "sec", "tec"}
    assert [c["login"] for c in client.get("/utilisateurs", headers=hb).json()] == ["admb"]
    # un compte d'un centre ne peut PAS choisir un autre centre par l'en-tête X-Centre
    triche = {**ha, "X-Centre": b["id"]}
    pa = nouveau_patient(client, ha)
    assert [p["id"] for p in client.get("/patients", headers=triche).json()] == [pa["id"]]
    # un administrateur de centre ne voit que son centre et ne peut pas en créer
    assert [c["id"] for c in client.get("/centres", headers=ha).json()] == [CENTRE]
    assert client.post("/centres", json={"nom": "X", "prefixe": "XX"}, headers=ha).status_code == 403


def test_compte_du_groupe_doit_choisir_un_centre(client):
    b, hb = _centre_b(client)
    r = client.post("/auth/login", json={"login": "sa", "mot_de_passe": "Motdepasse1"})
    sans = {"Authorization": "Bearer " + r.json()["jeton"]}
    assert r.json()["groupe"] is True
    assert client.get("/patients", headers=sans).status_code == 400                           # aucun centre choisi : aucune donnée
    assert len(client.get("/centres", headers=sans).json()) == 2                              # mais la liste des centres pour le sélecteur
    assert client.get("/patients", headers={**sans, "X-Centre": b["id"]}).status_code == 200
    assert client.get("/patients", headers={**sans, "X-Centre": "inconnu"}).status_code == 400


def test_journal_par_centre(client):
    b, hb = _centre_b(client)
    ha = entete(client, "adm")
    nouveau_patient(client, hb, nom="Zongo")
    assert not [l for l in client.get("/journal", headers=ha).json() if l["action"] == "patient_cree"]
    assert [l for l in client.get("/journal", headers=hb).json() if l["action"] == "patient_cree"]


def test_centre_desactive_ferme_l_acces(client):
    b, hb = _centre_b(client)
    hs = entete(client, "sa")
    assert client.put(f"/centres/{b['id']}", json={"actif": False}, headers=hs).status_code == 200
    assert client.get("/patients", headers=hb).status_code == 403


def test_prefixe_unique_et_verrouille(client):
    _centre_b(client)
    hs = entete(client, "sa")
    assert client.post("/centres", json={"nom": "Autre", "prefixe": "CMC"}, headers=hs).status_code == 409
    assert client.post("/centres", json={"nom": "Autre", "prefixe": "a!"}, headers=hs).status_code == 422


def test_migration_rattache_les_donnees_existantes(client):
    """Données d'avant le multi-centres (sans centre_id) : rattachées au centre initial, une seule fois."""
    brut = db.brut()
    brut.centres.delete_many({})
    brut.utilisateurs.update_many({}, {"$unset": {"centre_id": ""}})
    brut.patients.insert_one({"id": "vieux", "code": "DIAL-000009", "nom": "ANCIEN", "nom_norm": "ancien", "prenom_norm": "x", "statut": "actif"})
    amorcer_centre_initial()
    amorcer_centre_initial()                                                                  # idempotent
    assert brut.centres.count_documents({}) == 1 and brut.centres.find_one({})["id"] == CENTRE_INITIAL
    assert brut.patients.find_one({"id": "vieux"})["centre_id"] == CENTRE_INITIAL
    assert brut.utilisateurs.find_one({"login": "adm"})["centre_id"] == CENTRE_INITIAL
    assert brut.utilisateurs.find_one({"login": "sa"})["centre_id"] is None                  # le compte du groupe reste sans centre


def test_acces_sans_centre_refuse(client):
    db.fixer_centre(None)
    try:
        db.base().patients.find_one({})
        assert False, "un accès sans centre doit être refusé"
    except Exception as e:
        assert getattr(e, "status_code", None) == 400
    finally:
        db.fixer_centre(CENTRE)
