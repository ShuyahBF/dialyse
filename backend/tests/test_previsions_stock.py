"""Prévisions de rupture et bon de commande (lot 28) : calcul à date FIXÉE (jamais dépendant de l'heure réelle), droits, prix réservés à l'administration, PDF."""
from datetime import date, timedelta

from app import db, stock_prevision
from conftest import CENTRE, entete

JOUR = date(2030, 6, 15)                 # « aujourd'hui » des calculs
ISO = JOUR.isoformat()


def _article(nom, par_seance=0, seuil=0, code=None):
    a = {"id": "a-" + nom, "code": code or nom[:3].upper(), "nom": nom, "categorie": "Autre", "unite": "pièce", "seuil_alerte": seuil, "par_seance": par_seance, "actif": True, "stock": 0, "centre_id": CENTRE}
    db.brut().articles.insert_one(a)
    return a


def _lot(article, quantite, peremption="2032-01-01", cout=None, recu="2030-06-01"):
    db.brut().lots.insert_one({"id": f"l-{article['nom']}-{quantite}-{peremption}", "article_id": article["id"], "numero": f"L{quantite}{peremption}", "peremption": peremption,
                               "quantite_restante": quantite, "recu_le": recu, "cout_unitaire": cout, "centre_id": CENTRE})


def _sortie(article, quantite, jours_avant=3):
    db.brut().mouvements.insert_one({"id": f"m-{article['nom']}-{quantite}-{jours_avant}", "article_id": article["id"], "type": "sortie", "delta": -quantite,
                                     "date": (JOUR - timedelta(days=jours_avant)).isoformat(), "centre_id": CENTRE})


def _seances(n):
    for i in range(n):
        db.brut().seances.insert_one({"id": f"s{i}", "date": (JOUR + timedelta(days=1 + i % 20)).isoformat(), "statut": "planifiee", "centre_id": CENTRE})


def ligne(res, nom):
    return next(l for l in res["lignes"] if l["nom"] == nom)


def test_consommation_passee_prevision_et_quantite_a_commander(client):
    a = _article("Gants")                                   # pas « par séance » : on se fie à la consommation passée
    _lot(a, 40, cout=100)
    _sortie(a, 30)                                          # 30 sorties sur 30 jours = 1 par jour
    r = stock_prevision.calculer(couverture=30, aujourd_hui=JOUR)
    g = ligne(r, "Gants")
    assert g["conso_jour"] == 1 and g["jours_restants"] == 40 and g["rupture_estimee"] == (JOUR + timedelta(days=40)).isoformat()
    assert g["a_commander"] == 0 and g["statut"] == "ok"                   # 40 en stock couvrent les 30 jours prévus
    r60 = stock_prevision.calculer(couverture=60, aujourd_hui=JOUR)
    g60 = ligne(r60, "Gants")
    assert g60["a_commander"] == 20 and g60["statut"] == "a_commander" and g60["cout_estime"] == 2000       # 60 de besoin - 40 de stock, à 100 F


def test_article_par_seance_utilise_les_seances_planifiees(client):
    a = _article("Dialyseur", par_seance=1, seuil=5)
    _lot(a, 12)
    _seances(18)                                            # 18 séances planifiées dans les 30 jours
    d = ligne(stock_prevision.calculer(couverture=30, aujourd_hui=JOUR), "Dialyseur")
    assert d["besoin"] == 18 and d["a_commander"] == 11     # 18 + 5 de sécurité - 12 en stock
    assert d["jours_restants"] == 20 and d["statut"] == "a_commander"       # 12 / (18 par 30 jours) = 20 jours


def test_rupture_urgent_et_lots_perimes_ecartes(client):
    vide = _article("Aiguilles", seuil=10)                   # rien en stock, seuil de sécurité > 0
    perime = _article("Lignes")
    _lot(perime, 50, peremption="2030-01-01")                # lot PÉRIMÉ : n'est pas utilisable
    db.brut().articles.update_one({"id": perime["id"]}, {"$set": {"stock": 50}})            # le stock de l'article compte AUSSI les lots périmés (comme en vrai)
    _sortie(perime, 30)
    urgent = _article("Concentré")
    _lot(urgent, 3)
    _sortie(urgent, 30)                                      # 1 par jour, 3 en stock : 3 jours
    r = stock_prevision.calculer(couverture=30, aujourd_hui=JOUR)
    assert ligne(r, "Aiguilles")["statut"] == "rupture" and ligne(r, "Aiguilles")["a_commander"] == 10
    assert ligne(r, "Lignes")["stock"] == 0 and ligne(r, "Lignes")["stock_perime"] == 50            # 50 périmés signalés à part, 0 utilisable
    assert ligne(r, "Lignes")["statut"] == "rupture" and ligne(r, "Lignes")["a_commander"] == 30
    assert ligne(r, "Concentré")["statut"] == "urgent"
    ordre = [l["statut"] for l in r["lignes"]]
    assert ordre == sorted(ordre, key=lambda s: stock_prevision.ORDRE_STATUT[s])        # les plus urgents d'abord


def test_prix_du_dernier_lot_et_article_sans_prix_signale(client):
    a = _article("Héparine")
    _lot(a, 5, cout=800, recu="2030-01-01")
    _lot(a, 5, peremption="2032-02-01", cout=1000, recu="2030-05-01")            # plus récent : c'est son prix qui compte
    b = _article("Sérum")
    _lot(b, 1)
    for x in (a, b):
        _sortie(x, 60)
    r = stock_prevision.calculer(couverture=30, aujourd_hui=JOUR)
    assert ligne(r, "Héparine")["prix_unitaire"] == 1000
    assert ligne(r, "Sérum")["prix_unitaire"] is None and ligne(r, "Sérum")["cout_estime"] is None
    assert r["totaux"]["sans_prix"] == 1 and r["totaux"]["cout_estime"] == ligne(r, "Héparine")["cout_estime"]


def test_route_droits_prix_et_pdf(client):
    a = _article("Gants")
    _lot(a, 2, cout=500)
    db.brut().mouvements.insert_one({"id": "m-x", "article_id": a["id"], "type": "sortie", "delta": -30, "date": date.today().isoformat(), "centre_id": CENTRE})
    ha, hi, hm, hs = (entete(client, x) for x in ("adm", "inf", "med", "sec"))
    r_adm = client.get("/stock/previsions?couverture=30", headers=ha).json()
    assert r_adm["prix_visibles"] is True and "cout_estime" in r_adm["lignes"][0] and "cout_estime" in r_adm["totaux"]
    r_inf = client.get("/stock/previsions", headers=hi).json()
    assert r_inf["prix_visibles"] is False and "cout_estime" not in r_inf["lignes"][0] and "prix_unitaire" not in r_inf["lignes"][0] and "cout_estime" not in r_inf["totaux"]
    assert client.get("/stock/previsions", headers=hm).status_code == 200            # le médecin lit
    assert client.get("/stock/previsions", headers=hs).status_code == 403            # le secrétariat n'a pas accès au stock
    assert client.get("/stock/previsions?couverture=45", headers=ha).status_code == 422
    pdf = client.get("/stock/bon-commande?couverture=30", headers=ha)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"
    assert client.get("/stock/bon-commande", headers=hi).status_code == 200          # un infirmier peut commander (sans les prix)
    assert client.get("/stock/bon-commande", headers=hm).status_code == 403          # le médecin ne commande pas
    journal = [x["action"] for x in client.get("/journal", headers=ha).json()]
    assert "bon_commande_genere" in journal


def test_prevision_cloisonnee_par_centre(client):
    from test_multi_centres import _centre_b
    b, hb = _centre_b(client)
    a = _article("Gants")
    _lot(a, 1)
    assert client.get("/stock/previsions", headers=hb).json()["lignes"] == []         # le centre B ne voit ni les articles ni les stocks du centre A
