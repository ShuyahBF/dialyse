"""Activité du centre : réservations (confirmation = séance au calendrier), calendrier par jour, liste d'attente, pastilles de notifications du menu."""
import json
import time
from datetime import date, timedelta

import pytest

from app import db, whatsapp
from conftest import entete, nouveau_patient, nouveau_poste
from test_messagerie import CLE, _retour, wa  # noqa: F401  (fixture « wa » réutilisée)

DEMAIN = (date.today() + timedelta(days=1)).isoformat()


def _prep(client):
    h = entete(client, "sec")
    p = nouveau_patient(client, h, telephone="70123456")
    po = nouveau_poste(client, entete(client, "adm"))
    return h, p, po


def test_reservation_confirmee_cree_la_seance_au_calendrier(client, wa):
    h, p, po = _prep(client)
    client.put("/messagerie/parametres", json={"actif": True}, headers=entete(client, "adm"))                  # notifications automatiques activées par le centre
    r = client.post("/reservations", json={"patient_id": p["id"], "date": DEMAIN, "creneau": "matin", "motif": "Séance supplémentaire"}, headers=h)
    assert r.status_code == 200 and r.json()["statut"] == "demandee"
    rid = r.json()["id"]
    cal = client.get(f"/calendrier?du={DEMAIN}&au={DEMAIN}", headers=h).json()
    assert cal["jours"][0]["reservations_attente"] == 1 and cal["jours"][0]["planifiee"] == 0 and cal["capacite"] == 3
    c = client.post(f"/reservations/{rid}/confirmer", json={"poste_id": po["id"]}, headers=h)
    assert c.status_code == 200 and c.json()["statut"] == "confirmee" and c.json()["seance_id"]
    jour = client.get(f"/calendrier/jour?date={DEMAIN}", headers=h).json()
    case = next(x for x in jour["cellules"] if x["poste_id"] == po["id"] and x["creneau"] == "matin")
    assert case["seance"]["statut"] == "planifiee" and case["seance"]["patient"]["code"] == p["code"]
    assert next(x for x in jour["cellules"] if x["creneau"] == "soir")["seance"] is None                      # case libre
    assert any("CONFIRMÉE" in m["message"] for m in wa)                                                         # le patient est prévenu par WhatsApp
    cal = client.get(f"/calendrier?du={DEMAIN}&au={DEMAIN}", headers=h).json()["jours"][0]
    assert cal["planifiee"] == 1 and cal["occupation_pct"] == 33 and cal["reservations_confirmees"] == 1
    # annuler la réservation annule la séance
    assert client.post(f"/reservations/{rid}/annuler", json={}, headers=h).json()["statut"] == "annulee"
    assert client.get(f"/calendrier?du={DEMAIN}&au={DEMAIN}", headers=h).json()["jours"][0]["planifiee"] == 0


def test_controles_de_la_reservation(client, wa):
    h, p, po = _prep(client)
    hier = (date.today() - timedelta(days=1)).isoformat()
    assert client.post("/reservations", json={"patient_id": p["id"], "date": hier, "creneau": "matin"}, headers=h).status_code == 422          # date passée
    assert client.post("/reservations", json={"patient_id": "?", "date": DEMAIN, "creneau": "matin"}, headers=h).status_code == 404
    # poste déjà pris : la confirmation est refusée (contrôles du planning)
    q = nouveau_patient(client, h, nom="Zongo")
    client.post("/seances", json={"patient_id": q["id"], "poste_id": po["id"], "date": DEMAIN, "creneau": "matin"}, headers=h)
    r = client.post("/reservations", json={"patient_id": p["id"], "date": DEMAIN, "creneau": "matin"}, headers=h).json()
    assert client.post(f"/reservations/{r['id']}/confirmer", json={"poste_id": po["id"]}, headers=h).status_code == 409
    assert client.post(f"/reservations/{r['id']}/refuser", json={"motif": "Aucun poste libre"}, headers=h).json()["statut"] == "refusee"
    assert client.post(f"/reservations/{r['id']}/confirmer", json={"poste_id": po["id"]}, headers=h).status_code == 409                            # n'est plus en attente
    assert client.get("/reservations", headers=entete(client, "tec")).status_code == 403


def test_demande_whatsapp_convertie_en_reservation(client, wa):
    h, p, po = _prep(client)
    client.post("/messagerie/contacts", json={"nom": "OUEDRAOGO Awa", "numero": "70123456", "categorie": "patient", "patient_id": p["id"]}, headers=h)
    _retour(client, {"type": "reponse", "de": "+22670123456", "texte": "Bonjour je voudrais un rendez-vous"})
    d = client.get("/messagerie/demandes?statut=nouvelle", headers=h).json()[0]
    r = client.post("/reservations", json={"patient_id": p["id"], "date": DEMAIN, "creneau": "midi", "demande_id": d["id"], "poste_id": po["id"], "confirmer": True}, headers=h)
    assert r.status_code == 200 and r.json()["statut"] == "confirmee" and r.json()["source"] == "whatsapp"
    assert client.get("/messagerie/demandes?statut=nouvelle", headers=h).json() == []                                                              # demande traitée


def test_calendrier_borne_et_maintenance(client, wa):
    h, p, po = _prep(client)
    assert client.get("/calendrier?du=2026-01-01&au=2026-12-31", headers=h).status_code == 422
    client.put(f"/postes/{po['id']}", json={"prochaine_maintenance": DEMAIN}, headers=entete(client, "tec"))
    j = client.get(f"/calendrier?du={DEMAIN}&au={DEMAIN}", headers=h).json()["jours"][0]
    assert j["maintenances"] == [po["nom"]]
    # le secrétariat ne reçoit aucun détail médical dans la grille du jour
    q = client.post("/seances", json={"patient_id": p["id"], "poste_id": po["id"], "date": DEMAIN, "creneau": "soir"}, headers=h)
    assert q.status_code == 200
    case = next(x for x in client.get(f"/calendrier/jour?date={DEMAIN}", headers=h).json()["cellules"] if x["creneau"] == "soir")["seance"]
    assert "alertes" not in case or case["alertes"] is None


def test_liste_d_attente(client, wa):
    h = entete(client, "sec")
    a = client.post("/attente", json={"nom": "ilboudo", "prenom": "Awa", "telephone": "70000000", "motif": "Insuffisance rénale terminale", "priorite": "urgente"}, headers=h).json()
    client.post("/attente", json={"nom": "Zongo", "prenom": "Paul"}, headers=h)
    liste = client.get("/attente", headers=h).json()
    assert [x["nom"] for x in liste] == ["ILBOUDO", "ZONGO"]                                                     # urgente d'abord
    assert client.put(f"/attente/{a['id']}", json={"statut": "admis"}, headers=h).json()["statut"] == "admis"
    assert [x["nom"] for x in client.get("/attente", headers=h).json()] == ["ZONGO"]


def test_pastilles_de_notifications(client, wa):
    h, p, po = _prep(client)
    assert client.get("/notifications/compteurs", headers=h).json() == {}
    client.post("/messagerie/contacts", json={"nom": "OUEDRAOGO Awa", "numero": "70123456", "categorie": "patient"}, headers=h)
    _retour(client, {"type": "reponse", "de": "+22670123456", "texte": "Bonjour, je voudrais un rendez-vous"})
    client.post("/reservations", json={"patient_id": p["id"], "date": DEMAIN, "creneau": "matin"}, headers=h)
    c = client.get("/notifications/compteurs", headers=h).json()
    assert c["/messagerie"] == 1 and c["/reservations"] == 2                                                     # 1 demande WhatsApp nouvelle + 1 réservation demandée
    assert "/suivi" not in client.get("/notifications/compteurs", headers=h).json()                                # le secrétariat ne voit pas les alertes cliniques
    # un rôle sans messagerie ne voit pas ces pastilles
    assert "/messagerie" not in client.get("/notifications/compteurs", headers=entete(client, "inf")).json()
    # compte du groupe sans centre choisi : rien à compter
    r = client.post("/auth/login", json={"login": "sa", "mot_de_passe": "Motdepasse1"})
    assert client.get("/notifications/compteurs", headers={"Authorization": "Bearer " + r.json()["jeton"]}).json() == {}
