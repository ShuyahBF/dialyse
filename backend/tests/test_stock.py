"""Consommables et stocks : lots, FEFO, péremption, alertes, ajustements, consommation par séance, traçabilité (rappel de lot)."""
from datetime import date, timedelta

from app import stock as st
from conftest import entete, nouveau_patient, nouveau_poste

DEMAIN = (date.today() + timedelta(days=1)).isoformat()


def _article(client, h, nom="Dialyseur FX60", **extra):
    r = client.post("/stock/articles", json={"nom": nom, "categorie": "Dialyseur", "unite": "pièce", "seuil_alerte": 5, "par_seance": 1, **extra}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _entree(client, h, aid, q, lot, per="", **extra):
    return client.post("/stock/entrees", json={"article_id": aid, "quantite": q, "lot": lot, "peremption": per, **extra}, headers=h)


def test_fonctions_pures():
    assert st.statut_stock(0, 5) == "rupture" and st.statut_stock(5, 5) == "bas" and st.statut_stock(6, 5) == "ok"
    ref = date(2026, 6, 1)
    assert st.statut_peremption("2026-05-31", ref) == "perime" and st.statut_peremption("2026-07-15", ref) == "bientot"
    assert st.statut_peremption("2027-01-01", ref) == "ok" and st.statut_peremption("", ref) == "ok"


def test_droits(client):
    ha, hi, hm, hs = entete(client, "adm"), entete(client, "inf"), entete(client, "med"), entete(client, "sec")
    a = _article(client, hi)
    assert client.get("/stock/articles", headers=hm).status_code == 200                # le médecin lit
    assert client.post("/stock/articles", json={"nom": "X", "categorie": "Autre", "unite": "pièce"}, headers=hm).status_code == 403
    assert client.get("/stock/articles", headers=hs).status_code == 403                # le secrétariat n'a aucun accès
    assert client.delete(f"/stock/articles/{a['id']}", headers=hi).status_code == 403
    assert client.delete(f"/stock/articles/{a['id']}", headers=ha).status_code == 200


def test_entrees_lots_et_validations(client):
    hi = entete(client, "inf")
    a = _article(client, hi)
    assert a["code"] == "ART-001" and _article(client, hi, "Ligne à sang")["code"] == "ART-002"
    assert client.post("/stock/articles", json={"nom": "Dialyseur FX60", "categorie": "Dialyseur", "unite": "pièce"}, headers=hi).status_code == 409
    assert client.post("/stock/articles", json={"nom": "Y", "categorie": "Inconnue", "unite": "pièce"}, headers=hi).status_code == 422
    assert _entree(client, hi, a["id"], 10, "L1", "2030-01-01").status_code == 200
    assert _entree(client, hi, a["id"], 5, "L1").status_code == 200                       # complète le même lot
    assert _entree(client, hi, a["id"], 5, "L1", "2031-01-01").status_code == 409         # même lot, autre péremption : refusé
    assert _entree(client, hi, a["id"], 5, "").status_code == 422                          # lot obligatoire
    assert _entree(client, hi, a["id"], 0, "L2").status_code == 422
    d = client.get(f"/stock/articles/{a['id']}/lots", headers=hi).json()
    assert d["article"]["stock"] == 15 and len(d["lots"]) == 1 and d["lots"][0]["quantite_restante"] == 15 and len(d["mouvements"]) == 2


def test_sortie_fefo_et_stock_insuffisant(client):
    hi = entete(client, "inf")
    a = _article(client, hi)
    _entree(client, hi, a["id"], 4, "TARD", "2031-01-01")
    _entree(client, hi, a["id"], 4, "TOT", "2029-01-01")
    r = client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 6}, headers=hi).json()
    assert r["lots"] == [{"numero": "TOT", "quantite": 4}, {"numero": "TARD", "quantite": 2}]        # le plus proche de la péremption d'abord
    assert client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 3}, headers=hi).status_code == 409
    assert client.get(f"/stock/articles/{a['id']}/lots", headers=hi).json()["article"]["stock"] == 2        # rien retiré après l'échec
    assert client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 1, "type": "perte"}, headers=hi).status_code == 422      # motif obligatoire
    assert client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 1, "type": "perte", "motif": "Casse"}, headers=hi).status_code == 200


def test_lots_perimes_ignores_par_le_fefo_mais_sortables(client):
    hi = entete(client, "inf")
    a = _article(client, hi)
    _entree(client, hi, a["id"], 3, "PERIME", "2020-01-01")
    assert client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 1}, headers=hi).status_code == 409           # pas de sortie auto d'un périmé
    r = client.post("/stock/sorties", json={"article_id": a["id"], "quantite": 3, "lot": "PERIME", "type": "perte", "motif": "Périmé"}, headers=hi)
    assert r.status_code == 200 and client.get(f"/stock/articles/{a['id']}/lots", headers=hi).json()["article"]["stock"] == 0


def test_ajustement_inventaire(client):
    hi = entete(client, "inf")
    a = _article(client, hi)
    _entree(client, hi, a["id"], 10, "L1")
    assert client.post("/stock/ajustements", json={"article_id": a["id"], "lot": "L1", "quantite_constatee": 8}, headers=hi).status_code == 422      # motif obligatoire
    r = client.post("/stock/ajustements", json={"article_id": a["id"], "lot": "L1", "quantite_constatee": 8, "motif": "Inventaire de novembre"}, headers=hi).json()
    assert r["delta"] == -2 and r["type"] == "ajustement"
    assert client.post("/stock/ajustements", json={"article_id": a["id"], "lot": "ZZ", "quantite_constatee": 1, "motif": "x"}, headers=hi).status_code == 404
    assert client.get(f"/stock/articles/{a['id']}/lots", headers=hi).json()["article"]["stock"] == 8


def test_alertes(client):
    hi = entete(client, "inf")
    rupture = _article(client, hi, "Ligne à sang")                                         # stock 0 et consommé par séance
    bas = _article(client, hi, "Aiguilles")
    _entree(client, hi, bas["id"], 3, "A1", "2030-01-01")                                  # 3 ≤ seuil 5
    per = _article(client, hi, "Compresses", seuil_alerte=0, par_seance=0)
    _entree(client, hi, per["id"], 2, "C1", "2020-01-01")
    proche = _article(client, hi, "Gants", seuil_alerte=0, par_seance=0)
    _entree(client, hi, proche["id"], 2, "G1", (date.today() + timedelta(days=20)).isoformat())
    a = client.get("/stock/alertes", headers=hi).json()
    assert [x["nom"] for x in a["ruptures"]] == ["Ligne à sang"] and [x["nom"] for x in a["bas"]] == ["Aiguilles"]
    assert [x["lot"] for x in a["perimes"]] == ["C1"] and [x["lot"] for x in a["bientot_perimes"]] == ["G1"]
    liste = {x["nom"]: x for x in client.get("/stock/articles", headers=hi).json()}
    assert liste["Compresses"]["statut_peremption"] == "perime" and liste["Aiguilles"]["statut_stock"] == "bas"


def test_consommation_par_seance_et_tracabilite(client):
    hi, hm, ha = entete(client, "inf"), entete(client, "med"), entete(client, "adm")
    dial = _article(client, hi)
    ligne = _article(client, hi, "Ligne à sang")
    _entree(client, hi, dial["id"], 5, "LOT-D1", "2030-01-01")                              # la ligne à sang n'a AUCUN stock
    pat = nouveau_patient(client, hm)
    poste = nouveau_poste(client, ha)
    sid = client.post("/seances", json={"patient_id": pat["id"], "poste_id": poste["id"], "date": "2030-01-07", "creneau": "matin"}, headers=hm).json()["id"]
    s = client.post(f"/seances/{sid}/demarrer", json={"pre": {"poids": 60, "tension_sys": 120, "tension_dia": 80}}, headers=hi)
    assert s.status_code == 200                                                              # le manque de stock ne bloque pas le soin
    s = s.json()
    assert s["consommables"][0]["nom"] == "Dialyseur FX60" and s["consommables"][0]["lots"] == [{"numero": "LOT-D1", "quantite": 1}]
    assert s["manques"] == ["Ligne à sang"]
    assert client.get(f"/stock/articles/{dial['id']}/lots", headers=hi).json()["article"]["stock"] == 4
    # traçabilité : le lot LOT-D1 a servi pour ce patient
    t = client.get("/stock/tracabilite?lot=LOT-D1", headers=hm).json()
    assert len(t) == 1 and t[0]["code"] == pat["code"] and t[0]["poste"] == "Poste 1" and t[0]["date"] == "2030-01-07"
    assert client.get("/stock/tracabilite?lot=INCONNU", headers=hm).json() == []
    assert client.get("/stock/tracabilite?lot=LOT-D1", headers=entete(client, "tec")).status_code == 403       # le technicien n'a pas le nom des patients
    # le secrétariat ne voit ni consommables ni manques dans la séance
    vu = client.get(f"/seances/{sid}", headers=entete(client, "sec")).json()
    assert "consommables" not in vu and "manques" not in vu
    journal = client.get("/journal?action=tracabilite_lot", headers=ha).json()
    assert journal and journal[0]["detail"].startswith("lot LOT-D1")


def test_suppression_article_avec_mouvements_refusee(client):
    hi, ha = entete(client, "inf"), entete(client, "adm")
    a = _article(client, hi)
    _entree(client, hi, a["id"], 1, "L1")
    assert client.delete(f"/stock/articles/{a['id']}", headers=ha).status_code == 409
    assert client.put(f"/stock/articles/{a['id']}", json={"actif": False}, headers=hi).json()["actif"] is False
