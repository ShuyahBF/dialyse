"""Sauvegardes chiffrées : création vérifiée, corruption, clé, aperçu, restauration sûre, retour arrière automatique, journal conservé, droits."""
import pytest
from datetime import datetime, timezone

from app import db, sauvegardes as sv
from conftest import entete, nouveau_patient, nouveau_poste


def _creer(client, h):
    r = client.post("/admin/sauvegardes", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_creation_verifiee_et_chiffree(client):
    ha, hm = entete(client, "adm"), entete(client, "med")
    nouveau_patient(client, hm)
    f = _creer(client, ha)
    assert f["verifiee"] is True and f["origine"] == "manuelle" and f["cle_actuelle"] is True and f["compteurs"]["patients"] == 1 and f["total"] >= 7
    brut = sv._lire_octets(f["id"])
    assert b"OUEDRAOGO" not in brut and b"patients" not in brut                           # le contenu stocké est chiffré, illisible sans la clé
    e = client.get("/admin/sauvegardes", headers=ha).json()
    assert e["cle_configuree"] is True and len(e["sauvegardes"]) == 1 and "sha256" not in e["sauvegardes"][0]


def test_droits(client):
    ha, hm, hs = entete(client, "adm"), entete(client, "med"), entete(client, "sa")
    f = _creer(client, ha)
    assert client.get("/admin/sauvegardes", headers=hm).status_code == 403
    assert client.post("/admin/sauvegardes", headers=hm).status_code == 403
    # l'administrateur sauvegarde et vérifie ; seul le super administrateur restaure, télécharge, importe et supprime
    assert client.post(f"/admin/sauvegardes/{f['id']}/verifier", headers=ha).status_code == 200
    for methode, chemin in (("get", f"/admin/sauvegardes/{f['id']}/apercu"), ("get", f"/admin/sauvegardes/{f['id']}/fichier"), ("delete", f"/admin/sauvegardes/{f['id']}")):
        assert getattr(client, methode)(chemin, headers=ha).status_code == 403, chemin
    assert client.post(f"/admin/sauvegardes/{f['id']}/restaurer", json={"confirmation": "RESTAURER"}, headers=ha).status_code == 403
    assert client.post("/admin/sauvegardes/importer", content=b"x", headers=ha).status_code == 403
    assert client.get(f"/admin/sauvegardes/{f['id']}/apercu", headers=hs).status_code == 200


def test_corruption_detectee(client):
    ha = entete(client, "adm")
    f = _creer(client, ha)
    db.base().sauvegardes_morceaux.update_one({"sauvegarde_id": f["id"]}, {"$set": {"donnees": b"corrompu"}})
    r = client.post(f"/admin/sauvegardes/{f['id']}/verifier", headers=ha)
    assert r.status_code == 409 and "corrompue" in r.json()["detail"]
    assert client.get("/admin/sauvegardes", headers=ha).json()["sauvegardes"][0]["verifiee"] is False


def test_mauvaise_cle(client, monkeypatch):
    ha = entete(client, "adm")
    f = _creer(client, ha)
    monkeypatch.setenv("SAUVEGARDE_CLE", "une-autre-cle-de-chiffrement-456")
    s = client.get("/admin/sauvegardes", headers=ha).json()["sauvegardes"][0]
    assert s["cle_actuelle"] is False                                        # l'interface avertit que la clé a changé
    r = client.post(f"/admin/sauvegardes/{f['id']}/verifier", headers=ha)
    assert r.status_code == 400 and "clé" in r.json()["detail"]
    monkeypatch.setenv("SAUVEGARDE_CLE", "court")
    assert client.post("/admin/sauvegardes", headers=ha).status_code == 503   # clé absente ou trop courte : refus explicite
    assert client.get("/admin/sauvegardes", headers=ha).json()["cle_configuree"] is False


def test_apercu(client):
    ha, hm, hs = entete(client, "adm"), entete(client, "med"), entete(client, "sa")
    f = _creer(client, ha)
    nouveau_patient(client, hm)                                               # un patient de plus que dans la sauvegarde
    a = client.get(f"/admin/sauvegardes/{f['id']}/apercu", headers=hs).json()
    p = next(x for x in a["lignes"] if x["collection"] == "patients")
    assert (p["actuel"], p["sauvegarde"], p["ecart"]) == (1, 0, -1) and a["compte_present"] is True and a["confirmation"] == "RESTAURER"
    assert next(x for x in a["lignes"] if x["collection"] == "journal")["conservee"] is True
    assert client.get("/patients", headers=hm).json() != []                    # l'aperçu ne modifie rien


def test_restauration_complete(client):
    ha, hm, hs = entete(client, "adm"), entete(client, "med"), entete(client, "sa")
    p1 = nouveau_patient(client, hm)
    nouveau_poste(client, ha)
    f = _creer(client, ha)                                                     # sauvegarde avec 1 patient et 1 poste
    nouveau_patient(client, hm, nom="Sawadogo", prenom="Issa")
    client.delete(f"/postes/{client.get('/postes', headers=ha).json()[0]['id']}", headers=ha)
    assert len(client.get("/patients", headers=hm).json()) == 2
    assert client.post(f"/admin/sauvegardes/{f['id']}/restaurer", json={}, headers=hs).status_code == 400                 # confirmation obligatoire
    assert client.post(f"/admin/sauvegardes/{f['id']}/restaurer", json={"confirmation": "oui"}, headers=hs).status_code == 400
    r = client.post(f"/admin/sauvegardes/{f['id']}/restaurer", json={"confirmation": "RESTAURER"}, headers=hs)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert [p["code"] for p in client.get("/patients", headers=hm).json()] == [p1["code"]] and len(client.get("/postes", headers=ha).json()) == 1
    # une copie de sécurité de l'état d'AVANT (2 patients) a été créée et vérifiée : retour arrière possible
    secours = [s for s in client.get("/admin/sauvegardes", headers=hs).json()["sauvegardes"] if s["origine"] == "avant_restauration"]
    assert len(secours) == 1 and secours[0]["verifiee"] and secours[0]["compteurs"]["patients"] == 2
    r2 = client.post(f"/admin/sauvegardes/{secours[0]['id']}/restaurer", json={"confirmation": "RESTAURER"}, headers=hs)
    assert r2.status_code == 200 and len(client.get("/patients", headers=hm).json()) == 2                                  # retour arrière réussi


def test_journal_conserve_apres_restauration(client):
    ha, hm, hs = entete(client, "adm"), entete(client, "med"), entete(client, "sa")
    f = _creer(client, ha)
    nouveau_patient(client, hm)                                                # écrit « patient_cree » dans le journal APRÈS la sauvegarde
    client.post(f"/admin/sauvegardes/{f['id']}/restaurer", json={"confirmation": "RESTAURER"}, headers=hs)
    actions = [l["action"] for l in client.get("/journal?limite=1000", headers=ha).json()]
    assert "patient_cree" in actions and "restauration" in actions            # la preuve de ce qui s'est passé n'est jamais effacée


def test_retour_arriere_automatique_si_echec(client, monkeypatch):
    ha, hm, hs = entete(client, "adm"), entete(client, "med"), entete(client, "sa")
    nouveau_patient(client, hm)
    f = _creer(client, ha)
    nouveau_patient(client, hm, nom="Sawadogo", prenom="Issa")                 # état actuel : 2 patients
    vrai = sv._appliquer
    appels = {"n": 0}

    def tombe_en_panne(contenu):
        appels["n"] += 1
        if appels["n"] == 1:                                                   # la 1re application (la restauration) échoue À MOITIÉ
            db.base().patients.delete_many({})
            raise RuntimeError("panne simulée")
        vrai(contenu)                                                          # la 2e (le retour arrière) fonctionne
    monkeypatch.setattr(sv, "_appliquer", tombe_en_panne)
    r = client.post(f"/admin/sauvegardes/{f['id']}/restaurer", json={"confirmation": "RESTAURER"}, headers=hs)
    assert r.status_code == 500 and "remis automatiquement" in r.json()["detail"]
    assert len(client.get("/patients", headers=hm).json()) == 2                # AUCUNE donnée perdue
    assert any(l["action"] == "restauration_annulee" for l in client.get("/journal", headers=ha).json())


def test_restauration_refusee_si_compte_absent(client):
    ha, hs = entete(client, "adm"), entete(client, "sa")
    f = _creer(client, ha)
    # on retire le super administrateur de la sauvegarde stockée (simulation d'une vieille sauvegarde)
    contenu = sv.dechiffrer(sv._lire_octets(f["id"]))
    contenu["collections"]["utilisateurs"] = [u for u in contenu["collections"]["utilisateurs"] if u["role"] != "super_admin"]
    db.base().sauvegardes_morceaux.delete_many({"sauvegarde_id": f["id"]})
    donnees = sv.chiffrer(contenu)
    db.base().sauvegardes_morceaux.insert_one({"sauvegarde_id": f["id"], "n": 0, "donnees": donnees})
    import hashlib
    db.base().sauvegardes.update_one({"id": f["id"]}, {"$set": {"sha256": hashlib.sha256(donnees).hexdigest(), "compteurs": {**f["compteurs"], "utilisateurs": len(contenu["collections"]["utilisateurs"])}}})
    a = client.get(f"/admin/sauvegardes/{f['id']}/apercu", headers=hs).json()
    assert a["compte_present"] is False
    r = client.post(f"/admin/sauvegardes/{f['id']}/restaurer", json={"confirmation": "RESTAURER"}, headers=hs)
    assert r.status_code == 409 and "verrouiller" in r.json()["detail"]
    assert client.post("/auth/login", json={"login": "sa", "mot_de_passe": "Motdepasse1"}).status_code == 200      # toujours connecté


def test_export_et_import_de_fichier(client):
    ha, hm, hs = entete(client, "adm"), entete(client, "med"), entete(client, "sa")
    nouveau_patient(client, hm)
    f = _creer(client, ha)
    fichier = client.get(f"/admin/sauvegardes/{f['id']}/fichier", headers=hs)
    assert fichier.status_code == 200 and b"OUEDRAOGO" not in fichier.content and ".dialyse" in fichier.headers["content-disposition"]
    assert client.post("/admin/sauvegardes/importer", content=b"pas une sauvegarde", headers=hs).status_code == 400
    imp = client.post("/admin/sauvegardes/importer", content=fichier.content, headers=hs)
    assert imp.status_code == 200 and imp.json()["origine"] == "importee" and imp.json()["verifiee"] is True
    assert client.delete(f"/admin/sauvegardes/{imp.json()['id']}", headers=hs).status_code == 200
    assert client.delete(f"/admin/sauvegardes/{imp.json()['id']}", headers=hs).status_code == 404


def test_automatique_une_par_jour_apres_2h_et_retention(client):
    avant_2h = datetime(2030, 1, 7, 1, 59, tzinfo=timezone.utc)
    apres_2h = datetime(2030, 1, 7, 2, 5, tzinfo=timezone.utc)
    assert sv.sauvegarde_automatique(avant_2h) is False
    assert sv.sauvegarde_automatique(apres_2h) is True
    assert sv.sauvegarde_automatique(apres_2h) is False                        # une seule par jour
    auto = [s for s in db.base().sauvegardes.find({"origine": "auto"})]
    assert len(auto) == 1 and auto[0]["verifiee"] is True and auto[0]["par"] == "automatique"
    for i in range(20):                                                        # la rétention ne garde que les 14 plus récentes
        sv._ranger(b"x", {c: 0 for c in sv.COLLECTIONS}, "auto", "automatique")
    assert db.base().sauvegardes.count_documents({"origine": "auto"}) == sv.CONSERVER["auto"]
    assert db.base().sauvegardes_morceaux.count_documents({}) == sv.CONSERVER["auto"]           # les morceaux orphelins sont supprimés aussi
