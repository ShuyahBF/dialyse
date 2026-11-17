"""Dossier d'adhésion : modèles de pièces (par défaut + variantes de centre), réception des pièces, complétude, filtre, droits."""
from app import adhesion
from conftest import entete, nouveau_patient


def test_etat_dossier_pur():
    assert adhesion.etat_dossier(None, adhesion.PIECES_DEFAUT) == {"recues": 0, "total": 5, "complet": False, "manquantes": ["identite", "reference", "bilans", "serologies", "echographie"]}
    toutes = {c["cle"]: {"statut": "recue"} for c in adhesion.PIECES_DEFAUT if c["obligatoire"]}
    assert adhesion.etat_dossier(toutes, adhesion.PIECES_DEFAUT)["complet"] is True        # le certificat d'indigence est facultatif
    toutes["echographie"] = {"statut": "manquante"}
    assert adhesion.etat_dossier(toutes, adhesion.PIECES_DEFAUT)["manquantes"] == ["echographie"]


def test_pieces_validation_droits_et_filtre(client):
    hs, hm, ht = entete(client, "sec"), entete(client, "med"), entete(client, "tec")
    a, b = nouveau_patient(client, hs), nouveau_patient(client, hs, nom="Kabore", prenom="Issa")
    assert a["modele_adhesion"]["nom"].startswith("Modèle national")                       # modèle par défaut créé à la première lecture
    r = client.put(f"/patients/{a['id']}/pieces", json={"identite": {"statut": "recue", "date": "2026-11-01"}, "indigence": {"statut": "sans_objet"}}, headers=hs)
    assert r.status_code == 200 and r.json()["dossier_adhesion"]["recues"] == 1
    assert client.put(f"/patients/{a['id']}/pieces", json={"identite": {"statut": "sans_objet"}}, headers=hs).status_code == 422   # obligatoire : pas « sans objet »
    assert client.put(f"/patients/{a['id']}/pieces", json={"inconnue": {"statut": "recue"}}, headers=hs).status_code == 422
    assert client.put(f"/patients/{a['id']}/pieces", json={"bilans": {"statut": "recue", "date": "2999-01-01"}}, headers=hs).status_code == 422
    assert client.put(f"/patients/{a['id']}/pieces", json={"identite": {"statut": "recue"}}, headers=ht).status_code == 403
    tout = {c: {"statut": "recue", "date": "2026-11-02"} for c in ("identite", "reference", "bilans", "serologies", "echographie")}
    assert client.put(f"/patients/{a['id']}/pieces", json=tout, headers=hm).json()["dossier_adhesion"]["complet"] is True
    assert [x["id"] for x in client.get("/patients?dossier=incomplet", headers=hs).json()] == [b["id"]]
    assert "serologies" not in client.get(f"/patients/{a['id']}", headers=hs).json()      # aucun champ médical pour le secrétariat


def test_modeles_variantes_par_centre(client):
    ha, hs = entete(client, "adm"), entete(client, "sec")
    modeles = client.get("/modeles-adhesion", headers=hs).json()["modeles"]
    assert len(modeles) == 1 and modeles[0]["par_defaut"] and modeles[0]["patients"] == 0
    # seule l'administration crée / modifie
    assert client.post("/modeles-adhesion", json={"nom": "Centre Nord", "pieces": [{"libelle": "Carte d'identité", "obligatoire": True}]}, headers=hs).status_code == 403
    # variante : copie du modèle national + une pièce propre au centre, l'échographie devient facultative
    base = modeles[0]
    pieces = [dict(p, obligatoire=(p["cle"] != "echographie" and p["obligatoire"])) for p in base["pieces"]] + [{"libelle": "Attestation de résidence du chef de quartier", "obligatoire": True}]
    v = client.post("/modeles-adhesion", json={"nom": "Centre de Bobo-Dioulasso", "centre": "Bobo-Dioulasso", "pieces": pieces}, headers=ha)
    assert v.status_code == 200, v.text
    v = v.json(); cle_neuve = v["pieces"][-1]["cle"]
    p = nouveau_patient(client, hs)
    r = client.put(f"/patients/{p['id']}/modele-adhesion", json={"modele_id": v["id"]}, headers=hs).json()
    assert r["modele_adhesion"]["nom"] == "Centre de Bobo-Dioulasso" and r["dossier_adhesion"]["total"] == 5     # 4 obligatoires du national + attestation
    assert cle_neuve in r["dossier_adhesion"]["manquantes"]
    tout = {c: {"statut": "recue"} for c in ("identite", "reference", "bilans", "serologies", cle_neuve)}
    assert client.put(f"/patients/{p['id']}/pieces", json=tout, headers=hs).json()["dossier_adhesion"]["complet"] is True    # l'échographie n'est plus exigée ici
    # modifier : une pièce existante garde sa clé ; une nouvelle pièce reçoit une clé générée
    corps = {"nom": v["nom"], "pieces": v["pieces"] + [{"cle": "n_importe", "libelle": "Photo d'identité", "obligatoire": False}]}
    m2 = client.put(f"/modeles-adhesion/{v['id']}", json=corps, headers=ha).json()
    assert [x["cle"] for x in m2["pieces"][:-1]] == [x["cle"] for x in v["pieces"]] and m2["pieces"][-1]["cle"] != "n_importe"
    # suppression : refusée tant que des patients sont rattachés, et pour le modèle par défaut
    assert client.delete(f"/modeles-adhesion/{v['id']}", headers=ha).status_code == 409
    assert client.delete(f"/modeles-adhesion/{base['id']}", headers=ha).status_code == 409
    client.put(f"/patients/{p['id']}/modele-adhesion", json={"modele_id": base["id"]}, headers=hs)
    assert client.delete(f"/modeles-adhesion/{v['id']}", headers=ha).status_code == 200
    # validations
    assert client.post("/modeles-adhesion", json={"nom": "ab", "pieces": [{"libelle": "Une pièce", "obligatoire": True}]}, headers=ha).status_code == 422
    assert client.post("/modeles-adhesion", json={"nom": "Sans obligatoire", "pieces": [{"libelle": "Une pièce", "obligatoire": False}]}, headers=ha).status_code == 422
