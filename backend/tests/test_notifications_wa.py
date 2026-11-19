"""Notifications WhatsApp AUTOMATIQUES du patient (option par centre) : rendez-vous pris / annulé, séance terminée, rappel X heures avant, contrôle à renouveler."""
from datetime import date, datetime, timedelta, timezone

from app import db
from app.messagerie import rappels_automatiques
from conftest import entete, nouveau_patient, nouveau_poste
from test_messagerie import wa  # noqa: F401
from test_multi_centres import _centre_b

DEMAIN = (date.today() + timedelta(days=1)).isoformat()


def _prep(client):
    h = entete(client, "sec")
    p = nouveau_patient(client, h, telephone="70123456")
    po = nouveau_poste(client, entete(client, "adm"))
    return h, p, po


def _activer(client, **extra):
    r = client.put("/messagerie/parametres", json={"actif": True, **extra}, headers=entete(client, "adm"))
    assert r.status_code == 200, r.text
    return r.json()


def test_reglages_par_defaut_et_droits(client, wa):
    p = client.get("/messagerie/parametres", headers=entete(client, "sec")).json()
    assert p["actif"] is False and p["rappel_heures_avant"] == 1 and p["evenements"]["rappel"] is True and p["evenements"]["renouvellement"] is False
    assert len(p["liste"]) == 7
    assert client.put("/messagerie/parametres", json={"actif": True}, headers=entete(client, "sec")).status_code == 403          # réglage : administration
    assert client.put("/messagerie/parametres", json={"rappel_heures_avant": 0}, headers=entete(client, "adm")).status_code == 422
    assert client.put("/messagerie/parametres", json={"rappel_heures_avant": 99}, headers=entete(client, "adm")).status_code == 422
    assert _activer(client, rappel_heures_avant=3)["rappel_heures_avant"] == 3


def test_rien_ne_part_tant_que_l_option_est_eteinte(client, wa):
    h, p, po = _prep(client)
    r = client.post("/reservations", json={"patient_id": p["id"], "date": DEMAIN, "creneau": "matin", "poste_id": po["id"], "confirmer": True}, headers=h)
    assert r.status_code == 200 and wa == []
    _activer(client, evenements={"reservation_annulee": False})
    client.post(f"/reservations/{r.json()['id']}/annuler", json={}, headers=h)
    assert wa == []                                                                                                          # événement désactivé : rien


def test_rendez_vous_pris_annule_et_seance_terminee(client, wa):
    h, p, po = _prep(client)
    _activer(client)
    r = client.post("/reservations", json={"patient_id": p["id"], "date": DEMAIN, "creneau": "midi", "poste_id": po["id"], "confirmer": True}, headers=h).json()
    assert "CONFIRMÉE" in wa[-1]["message"] and "12:00" in wa[-1]["message"] and "Centre principal" in wa[-1]["message"]
    assert wa[-1]["message"].count("{") == 0                                                                                   # toutes les variables remplacées
    client.post(f"/reservations/{r['id']}/annuler", json={}, headers=h)
    assert "ANNULÉE" in wa[-1]["message"]
    # séance annulée par le planning
    s = client.post("/seances", json={"patient_id": p["id"], "poste_id": po["id"], "date": DEMAIN, "creneau": "soir"}, headers=h).json()
    client.post(f"/seances/{s['id']}/annuler", json={"motif": "Panne"}, headers=h)
    assert "ANNULÉE" in wa[-1]["message"] and "soir" in wa[-1]["message"]
    # séance terminée
    s2 = client.post("/seances", json={"patient_id": p["id"], "poste_id": po["id"], "date": date.today().isoformat(), "creneau": "matin"}, headers=h).json()
    hi = entete(client, "inf")
    client.post(f"/seances/{s2['id']}/demarrer", json={"pre": {"poids": 70, "tension_sys": 120, "tension_dia": 80}}, headers=hi)
    n = len(wa)
    client.post(f"/seances/{s2['id']}/terminer", json={"post": {"poids": 68, "volume_uf_l": 2, "kt_v": 1.3, "duree_reelle_min": 240}}, headers=hi)
    assert len(wa) == n + 1 and "terminée" in wa[-1]["message"]
    assert not any(w in wa[-1]["message"].lower() for w in ("poids", "kt", "tension"))                                          # aucune donnée médicale


def test_rappel_x_heures_avant_une_seule_fois(client, wa):
    h, p, po = _prep(client)
    auj = date.today().isoformat()
    client.post("/seances", json={"patient_id": p["id"], "poste_id": po["id"], "date": auj, "creneau": "matin"}, headers=h)             # 07:00
    t6h = datetime.fromisoformat(f"{auj}T06:00:00+00:00")
    assert rappels_automatiques(t6h) == 0                                                                                    # option éteinte
    _activer(client, rappel_heures_avant=1)
    assert rappels_automatiques(datetime.fromisoformat(f"{auj}T05:00:00+00:00")) == 0                                        # trop tôt (2 h avant)
    assert rappels_automatiques(t6h) == 1 and "commence à 07:00" in wa[-1]["message"] and "CONFIRMER" in wa[-1]["message"]
    assert rappels_automatiques(t6h) == 0                                                                                    # un seul rappel par séance
    assert rappels_automatiques(datetime.fromisoformat(f"{auj}T07:30:00+00:00")) == 0                                        # séance déjà commencée : jamais de rappel tardif


def test_rappel_heure_parametrable_et_par_centre(client, wa):
    b, hb = _centre_b(client)
    h, p, po = _prep(client)
    auj = date.today().isoformat()
    client.post("/seances", json={"patient_id": p["id"], "poste_id": po["id"], "date": auj, "creneau": "midi"}, headers=h)             # 12:00
    _activer(client, rappel_heures_avant=3)
    assert rappels_automatiques(datetime.fromisoformat(f"{auj}T09:30:00+00:00")) == 1                                        # 2 h 30 avant, réglage 3 h
    # le centre B n'a pas activé l'option : rien pour lui, et ses réglages sont les siens
    assert client.get("/messagerie/parametres", headers=hb).json()["actif"] is False


def test_pas_de_message_sans_numero_ou_desinscrit(client, wa):
    h = entete(client, "sec")
    p = nouveau_patient(client, h, telephone="")
    po = nouveau_poste(client, entete(client, "adm"))
    _activer(client)
    client.post("/reservations", json={"patient_id": p["id"], "date": DEMAIN, "creneau": "matin", "poste_id": po["id"], "confirmer": True}, headers=h)
    assert wa == []
    q = nouveau_patient(client, h, nom="Zongo", telephone="70999999")
    client.post("/messagerie/contacts", json={"nom": "ZONGO", "numero": "70999999", "patient_id": q["id"]}, headers=h)
    from conftest import CENTRE
    db.base().contacts.update_one({"numero": "22670999999"}, {"$set": {"desinscrit": True}})
    client.post("/reservations", json={"patient_id": q["id"], "date": DEMAIN, "creneau": "midi", "poste_id": po["id"], "confirmer": True}, headers=h)
    assert wa == []                                                                                                          # STOP respecté


def test_modeles_automatiques_ajoutes_une_fois(client, wa):
    h = entete(client, "sec")
    noms = {m["nom"] for m in client.get("/messagerie/modeles", headers=h).json()}
    assert {"Réservation confirmée", "Séance terminée", "Rappel avant la séance", "Contrôle à renouveler"} <= noms
    m = next(x for x in client.get("/messagerie/modeles", headers=h).json() if x["nom"] == "Séance terminée")
    client.delete(f"/messagerie/modeles/{m['id']}", headers=h)
    assert "Séance terminée" not in {x["nom"] for x in client.get("/messagerie/modeles", headers=h).json()}                  # supprimé : ne revient pas


def test_controle_a_renouveler(client, wa):
    from app import messagerie
    h, p, po = _prep(client)
    _activer(client, evenements={"renouvellement": True, "rappel": False})
    messagerie._DERNIER_RENOUVELLEMENT.clear()
    now = datetime.now(timezone.utc)
    assert rappels_automatiques(now) == 1 and "contrôle de suivi" in wa[-1]["message"]                                       # aucun bilan : à renouveler
    messagerie._DERNIER_RENOUVELLEMENT.clear()
    assert rappels_automatiques(now + timedelta(days=1)) == 0                                                                # relancé il y a moins de 14 jours
    messagerie._DERNIER_RENOUVELLEMENT.clear()
    assert rappels_automatiques(now + timedelta(days=15)) == 1                                                               # 14 jours plus tard : nouvelle relance
