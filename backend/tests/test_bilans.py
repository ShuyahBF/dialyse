"""Bilans biologiques : interprétation, URR, droits, évolution, suivi des bilans en retard et critiques."""
from datetime import date, timedelta

from app import bilans_ref as ref
from conftest import entete, nouveau_patient


def test_interpretation_pure():
    assert ref.interpreter("potassium", 4.5) == "normal"
    assert ref.interpreter("potassium", 5.8) == "haut"
    assert ref.interpreter("potassium", 6.2) == "critique_haut"
    assert ref.interpreter("potassium", 2.9) == "critique_bas"
    assert ref.interpreter("hemoglobine", 9) == "bas"
    assert ref.interpreter("hemoglobine", 6.5) == "critique_bas"
    assert ref.interpreter("creatinine", 900) == "normal"          # pas de cible : jamais d'alerte
    assert ref.urr(25, 8) == 68.0 and ref.urr(None, 8) is None and ref.urr(0, 0) is None


def test_analyse_alertes():
    a = ref.analyser({"potassium": 6.3, "hemoglobine": 9.2, "uree_pre": 30, "uree_post": 15})
    niveaux = {x["niveau"]: x["message"] for x in a["alertes"]}
    assert "Potassium critique" in niveaux["critique"]
    assert any("Hémoglobine basse" in x["message"] for x in a["alertes"])
    assert any("URR insuffisant" in x["message"] for x in a["alertes"]) and a["urr"] == 50.0


def _bilan(client, h, pid, jour, **res):
    return client.post(f"/patients/{pid}/bilans", json={"date_prelevement": jour, "type": "Mensuel", "resultats": res}, headers=h)


def test_creation_droits_et_validation(client):
    hm, hi, hs, ht = entete(client, "med"), entete(client, "inf"), entete(client, "sec"), entete(client, "tec")
    p = nouveau_patient(client, hm)
    r = _bilan(client, hi, p["id"], "2026-01-10", potassium=6.4, hemoglobine=10.5)
    assert r.status_code == 200 and r.json()["analyse"]["lignes"]["potassium"]["statut"] == "critique_haut"
    assert _bilan(client, hs, p["id"], "2026-01-10", potassium=4).status_code == 403           # secrétariat : aucun accès
    assert client.get(f"/patients/{p['id']}/bilans", headers=hs).status_code == 403
    assert client.get(f"/patients/{p['id']}/bilans", headers=ht).status_code == 403
    assert _bilan(client, hm, p["id"], "2026-01-10", inconnu=3).status_code == 422             # paramètre hors catalogue
    assert _bilan(client, hm, p["id"], "2026-01-10").status_code == 422                        # au moins un résultat
    assert _bilan(client, hm, p["id"], "2999-01-01", potassium=4).status_code == 422           # pas de date future
    assert _bilan(client, hm, p["id"], "2026-01-10", potassium="abc").status_code == 422
    assert _bilan(client, hm, "inconnu", "2026-01-10", potassium=4).status_code == 404


def test_correction_medecin_seulement_et_historique(client):
    hm, hi, ha = entete(client, "med"), entete(client, "inf"), entete(client, "adm")
    p = nouveau_patient(client, hm)
    b = _bilan(client, hi, p["id"], "2026-01-10", potassium=6.4).json()
    assert client.put(f"/bilans/{b['id']}", json={"resultats": {"potassium": 4.4}}, headers=hi).status_code == 403
    r = client.put(f"/bilans/{b['id']}", json={"resultats": {"potassium": 4.4}}, headers=hm).json()
    assert r["analyse"]["lignes"]["potassium"]["statut"] == "normal"
    h = client.get(f"/historique/bilans/{b['id']}", headers=ha).json()
    assert any("resultats" in x["champs"] for x in h["lignes"]) and "4.4" not in str(h)
    assert client.delete(f"/bilans/{b['id']}", headers=hm).status_code == 403
    assert client.delete(f"/bilans/{b['id']}", headers=ha).status_code == 200


def test_evolution_et_urr(client):
    hm = entete(client, "med")
    p = nouveau_patient(client, hm)
    _bilan(client, hm, p["id"], "2026-02-10", potassium=4.0, uree_pre=30, uree_post=9)
    _bilan(client, hm, p["id"], "2026-01-10", potassium=6.5, uree_pre=30, uree_post=15)
    serie = client.get(f"/patients/{p['id']}/bilans/evolution/potassium", headers=hm).json()
    assert [x["date"] for x in serie] == ["2026-01-10", "2026-02-10"] and serie[0]["statut"] == "critique_haut"
    urr = client.get(f"/patients/{p['id']}/bilans/evolution/urr", headers=hm).json()
    assert [x["valeur"] for x in urr] == [50.0, 70.0] and urr[1]["statut"] == "normal"
    assert client.get(f"/patients/{p['id']}/bilans/evolution/zzz", headers=hm).status_code == 404
    lst = client.get(f"/patients/{p['id']}/bilans", headers=hm).json()
    assert [x["date_prelevement"] for x in lst] == ["2026-02-10", "2026-01-10"]            # le plus récent d'abord


def test_suivi_en_retard_et_critiques(client):
    hm = entete(client, "med")
    recent = (date.today() - timedelta(days=5)).isoformat()
    ancien = (date.today() - timedelta(days=90)).isoformat()
    a = nouveau_patient(client, hm, nom="Alpha", prenom="A")                # bilan récent et critique
    b = nouveau_patient(client, hm, nom="Bravo", prenom="B")                # bilan ancien
    c = nouveau_patient(client, hm, nom="Charlie", prenom="C")              # aucun bilan
    _bilan(client, hm, a["id"], recent, potassium=6.5)
    _bilan(client, hm, b["id"], ancien, potassium=4.0)
    s = client.get("/bilans/suivi", headers=hm).json()
    retard = {x["nom"]: x["dernier_bilan"] for x in s["en_retard"]}
    assert set(retard) == {"BRAVO", "CHARLIE"} and retard["CHARLIE"] == ""
    assert [x["nom"] for x in s["critiques"]] == ["ALPHA"]
    assert client.get("/bilans/suivi", headers=entete(client, "sec")).status_code == 403


def test_catalogue(client):
    r = client.get("/bilans/parametres", headers=entete(client, "inf")).json()
    assert any(p["cle"] == "potassium" and p["unite"] == "mmol/L" for p in r["parametres"]) and r["urr_cible"] == 65
    assert client.get("/bilans/parametres", headers=entete(client, "sec")).status_code == 403
