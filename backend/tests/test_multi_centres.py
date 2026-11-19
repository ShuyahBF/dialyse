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


# ---------- fiche du centre : logo, responsable, papier à en-tête A4 / A5, géolocalisation ----------

def _png(taille=(300, 120), couleur=(200, 30, 30)):
    """Petit PNG en « data URL » fabriqué pour les tests."""
    import base64
    import io
    from PIL import Image
    t = io.BytesIO()
    Image.new("RGB", taille, couleur).save(t, "PNG")
    return "data:image/png;base64," + base64.b64encode(t.getvalue()).decode()


def test_fiche_du_centre_et_logo(client):
    ha = entete(client, "adm")
    corps = {"responsable": "Dr OUEDRAOGO Awa", "titre_responsable": "Directrice", "adresse": "Secteur 15, Ouagadougou", "telephone": "25 30 00 00",
             "email": "awa.badini@gmail.com", "latitude": 12.3714, "longitude": -1.5197, "logo": _png()}
    r = client.put("/centre", json=corps, headers=ha)
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["responsable"] == "Dr OUEDRAOGO Awa" and f["latitude"] == 12.3714 and f["a_logo"] and f["logo"].startswith("data:image/png;base64,")
    assert client.get("/centre", headers=ha).json()["logo"] == f["logo"]
    assert "logo" not in client.get("/centres", headers=ha).json()[0]               # jamais de logo dans les listes
    # le nom, le préfixe et l'état restent au super administrateur
    client.put("/centre", json={"nom": "Autre nom", "prefixe": "ZZ", "actif": False}, headers=ha)
    assert client.get("/centre", headers=ha).json()["nom"] == "Centre principal"
    # retrait du logo
    assert client.put("/centre", json={"logo": ""}, headers=ha).json()["a_logo"] is False


def test_logo_et_geolocalisation_controles(client):
    ha = entete(client, "adm")
    assert client.put("/centre", json={"logo": "data:image/png;base64,AAAA"}, headers=ha).status_code == 422          # pas une vraie image
    assert client.put("/centre", json={"logo": "data:image/gif;base64,R0lGODlhAQABAAAAACw="}, headers=ha).status_code == 422
    assert client.put("/centre", json={"latitude": 120, "longitude": 0}, headers=ha).status_code == 422
    assert client.put("/centre", json={"latitude": "abc", "longitude": 0}, headers=ha).status_code == 422
    gros = _png((2000, 2000))
    assert client.put("/centre", json={"logo": gros}, headers=ha).status_code in (200, 422)                           # réduit à 480 px si la taille le permet
    # un logo réduit ne dépasse jamais 480 px
    import base64, io
    from PIL import Image
    f = client.put("/centre", json={"logo": _png((900, 300))}, headers=ha).json()
    assert max(Image.open(io.BytesIO(base64.b64decode(f["logo"].split(",")[1]))).size) <= 480


def test_papier_a_entete_a4_et_a5(client):
    ha = entete(client, "adm")
    client.put("/centre", json={"responsable": "Dr OUEDRAOGO Awa", "adresse": "Secteur 15", "latitude": 12.37, "longitude": -1.52, "logo": _png()}, headers=ha)
    for fmt, (l, h) in (("A4", (595, 842)), ("A5", (420, 595))):
        r = client.get(f"/centre/papier-entete?format={fmt}", headers=ha)
        assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["content-disposition"].startswith("inline")
        assert f"/MediaBox [0 0 {l}".encode() in r.content or b"/MediaBox" in r.content
    assert client.get("/centre/papier-entete?format=A3", headers=ha).status_code == 422
    assert client.get("/centre/papier-entete", headers=entete(client, "tec")).status_code == 403


def test_la_fiche_d_un_centre_ne_fuit_pas_vers_l_autre(client):
    b, hb = _centre_b(client)
    ha = entete(client, "adm")
    client.put("/centre", json={"responsable": "Dr A", "logo": _png()}, headers=ha)
    assert client.get("/centre", headers=hb).json()["responsable"] == "" and client.get("/centre", headers=hb).json()["a_logo"] is False
    hs = entete(client, "sa")
    assert client.get(f"/centres/{b['id']}", headers=hs).json()["nom"] == "Clinique Pilote"
    assert client.get(f"/centres/{b['id']}", headers=ha).status_code == 403


def test_rapport_pdf_avec_logo_du_centre(client):
    ha = entete(client, "adm")
    client.put("/centre", json={"responsable": "Dr OUEDRAOGO Awa", "logo": _png()}, headers=ha)
    r = client.get("/rapports/pdf?du=2026-11-01&au=2026-11-30", headers=ha)
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and b"/Image" in r.content          # le logo du centre est dans le PDF
