"""Administrateur multi-centres (lot 26) : un administrateur peut travailler dans plusieurs centres, ceux que le super administrateur lui a donnés, et aucun autre."""
from app import db, securite
from conftest import entete, nouveau_patient


def _deux_centres(client):
    """Centres B et C créés par le super administrateur ; « adm » (centre principal) y reçoit B, jamais C."""
    hs = entete(client, "sa")
    b = client.post("/centres", json={"nom": "Clinique B", "prefixe": "cmb"}, headers=hs).json()
    c = client.post("/centres", json={"nom": "Clinique C", "prefixe": "cmc"}, headers=hs).json()
    return hs, b, c


def _donner(client, hs, centres_ids, login="adm"):
    compte = next(x for x in client.get("/utilisateurs", headers=hs).json() if x["login"] == login)
    return client.put(f"/utilisateurs/{compte['id']}", json={"centres_ids": centres_ids}, headers=hs)


def test_le_super_administrateur_donne_un_centre_de_plus(client):
    hs, b, c = _deux_centres(client)
    r = _donner(client, hs, [b["id"]])
    assert r.status_code == 200 and r.json()["centres_ids"] == [b["id"]]
    ha = entete(client, "adm")
    moi = client.get("/me", headers=ha).json()
    assert moi["multi_centres"] is True and moi["centre_principal"] and set(moi["centres_ids"]) == {moi["centre_principal"], b["id"]}
    # la liste des centres ne contient QUE les siens
    assert {x["id"] for x in client.get("/centres", headers=ha).json()} == set(moi["centres_ids"])


def test_il_travaille_dans_le_centre_choisi_et_sans_choix_dans_le_sien(client):
    hs, b, c = _deux_centres(client)
    _donner(client, hs, [b["id"]])
    ha = entete(client, "adm")
    chez_a = nouveau_patient(client, ha)
    assert chez_a["code"].startswith("DIAL-")                                          # sans choix : son centre principal
    chez_b = nouveau_patient(client, {**ha, "X-Centre": b["id"]}, nom="Zongo")
    assert chez_b["code"] == "CMB-000001"                                              # centre B : son propre compteur
    assert [p["id"] for p in client.get("/patients", headers=ha).json()] == [chez_a["id"]]
    assert [p["id"] for p in client.get("/patients", headers={**ha, "X-Centre": b["id"]}).json()] == [chez_b["id"]]
    assert client.get("/me", headers={**ha, "X-Centre": b["id"]}).json()["centre_id"] == b["id"]


def test_un_centre_hors_de_sa_liste_est_refuse(client):
    hs, b, c = _deux_centres(client)
    _donner(client, hs, [b["id"]])
    ha = entete(client, "adm")
    assert client.get("/patients", headers={**ha, "X-Centre": c["id"]}).status_code == 403
    assert client.get("/patients", headers={**ha, "X-Centre": "centre-inconnu"}).status_code == 403


def test_un_compte_ordinaire_n_a_toujours_pas_le_choix(client):
    hs, b, c = _deux_centres(client)
    _donner(client, hs, [b["id"]])
    hm = entete(client, "med")
    assert client.get("/me", headers=hm).json()["multi_centres"] is False
    assert [x["id"] for x in client.get("/centres", headers=hm).json()] != []
    assert client.get("/patients", headers={**hm, "X-Centre": b["id"]}).status_code == 200      # en-tête ignoré : il reste dans son centre
    assert client.get("/me", headers={**hm, "X-Centre": b["id"]}).json()["centre_id"] != b["id"]


def test_seul_le_super_administrateur_attribue_des_centres(client):
    hs, b, c = _deux_centres(client)
    ha = entete(client, "adm")
    med = next(x for x in client.get("/utilisateurs", headers=ha).json() if x["login"] == "med")
    assert client.put(f"/utilisateurs/{med['id']}", json={"centres_ids": [b["id"]]}, headers=ha).status_code == 403
    adm = next(x for x in client.get("/utilisateurs", headers=hs).json() if x["login"] == "adm")
    assert client.put(f"/utilisateurs/{adm['id']}", json={"centres_ids": [b["id"]]}, headers=ha).status_code in (403, 404)   # pas même pour soi


def test_controles_des_centres_attribues(client):
    hs, b, c = _deux_centres(client)
    assert _donner(client, hs, ["inexistant"]).status_code == 422                       # un centre qui n'existe pas
    assert _donner(client, hs, [], login="med").status_code == 200                      # liste vide : rien à attribuer
    assert _donner(client, hs, [b["id"]], login="med").status_code == 422              # seul un administrateur peut en avoir
    assert _donner(client, hs, [b["id"], b["id"]]).json()["centres_ids"] == [b["id"]]  # doublons retirés


def test_retirer_les_centres_ou_changer_de_role_remet_le_compte_dans_son_centre(client):
    hs, b, c = _deux_centres(client)
    _donner(client, hs, [b["id"]])
    assert _donner(client, hs, []).json()["centres_ids"] == []
    ha = entete(client, "adm")
    assert client.get("/me", headers=ha).json()["multi_centres"] is False
    assert client.get("/patients", headers={**ha, "X-Centre": b["id"]}).status_code == 200      # en-tête ignoré : plus de choix
    _donner(client, hs, [b["id"]])
    adm = next(x for x in client.get("/utilisateurs", headers=hs).json() if x["login"] == "adm")
    assert client.put(f"/utilisateurs/{adm['id']}", json={"role": "medecin"}, headers=hs).json()["centres_ids"] == []


def test_les_comptes_geres_sont_ceux_du_centre_de_travail(client):
    hs, b, c = _deux_centres(client)
    _donner(client, hs, [b["id"]])
    ha = entete(client, "adm")
    hb = {**ha, "X-Centre": b["id"]}
    r = client.post("/utilisateurs", json={"login": "nouvelle", "nom_affiche": "OUEDRAOGO Awa", "role": "infirmier", "mot_de_passe": "Provisoire1"}, headers=hb)
    assert r.status_code == 200 and r.json()["centre_id"] == b["id"]                    # le compte naît dans le centre B, où il travaille
    assert [x["login"] for x in client.get("/utilisateurs", headers=hb).json()] == ["nouvelle"]
    assert "nouvelle" not in [x["login"] for x in client.get("/utilisateurs", headers=ha).json()]
