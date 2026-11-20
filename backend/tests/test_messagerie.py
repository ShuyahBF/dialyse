"""Centre de messagerie WhatsApp : contacts, envoi (texte et documents), STOP, réponses, réservations, rappels, retours signés, étanchéité entre centres."""
import json
import time

import pytest

from app import db, whatsapp
from conftest import CENTRE, entete, nouveau_patient
from test_multi_centres import _centre_b

CLE = "cle-hmac-de-test-liluvine-123456"


@pytest.fixture()
def wa(client, monkeypatch):
    """WhatsApp configuré ; aucun appel réseau : les envois sont notés dans `envoyes`."""
    monkeypatch.setenv("LILUVINE_WA_URL", "https://sawali.test/liluvine-send")
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    envoyes = []

    def faux(url, entetes, corps):
        envoyes.append(json.loads(corps))
        return 200, {"ok": True}
    monkeypatch.setattr(whatsapp, "_appel_http", faux)
    return envoyes


def _retour(client, corps):
    """Appel signé comme le fait SAWALI (X-Timestamp, X-Signature = HMAC-SHA256(clé, « horodatage.corps »))."""
    brut = json.dumps(corps, ensure_ascii=False, separators=(",", ":"))
    ts = str(int(time.time()))
    return client.post("/api/webhooks/liluvine-retour", content=brut.encode(), headers={"X-Timestamp": ts, "X-Signature": whatsapp.signer(CLE, ts, brut), "Content-Type": "application/json"})


def _contact(client, h, numero="70123456", nom="OUEDRAOGO Awa", **extra):
    r = client.post("/messagerie/contacts", json={"nom": nom, "numero": numero, "categorie": "patient", **extra}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_contacts_et_import_des_patients(client, wa):
    h = entete(client, "sec")
    nouveau_patient(client, h, telephone="70 11 22 33")
    nouveau_patient(client, h, nom="Zongo", telephone="abc")
    r = client.post("/messagerie/contacts/importer-patients", headers=h)
    assert r.json() == {"crees": 1, "sans_numero_valide": 1}
    assert client.post("/messagerie/contacts/importer-patients", headers=h).json()["crees"] == 0                      # pas de doublon
    c = client.get("/messagerie/contacts", headers=h).json()[0]
    assert c["numero"] == "22670112233" and c["categorie"] == "patient"
    assert client.post("/messagerie/contacts", json={"nom": "X", "numero": "70112233"}, headers=h).status_code == 409
    assert client.post("/messagerie/contacts", json={"nom": "X", "numero": "12"}, headers=h).status_code == 422
    assert client.get("/messagerie/contacts", headers=entete(client, "inf")).status_code == 403                       # rôles de la messagerie


def test_envoi_texte_document_et_variables(client, wa):
    h = entete(client, "sec")
    c = _contact(client, h)
    r = client.post("/messagerie/envoyer", json={"contact_id": c["id"], "texte": "Bonjour {prenom}, centre {centre}"}, headers=h)
    assert r.status_code == 200, r.text
    assert wa[0]["to"] == "+22670123456" and wa[0]["message"] == "Bonjour Awa, centre Centre principal" and wa[0]["source"] == "Dialyse"
    conv = client.get(f"/messagerie/contacts/{c['id']}/messages", headers=h).json()
    assert conv["messages"][0]["statut"] == "envoye"
    # documents : papier à en-tête et fichier
    r = client.post("/messagerie/envoyer", json={"contact_id": c["id"], "texte": "", "document": {"type": "papier", "format": "A5"}}, headers=h)
    assert r.status_code == 200 and wa[1]["media"]["type"] == "document" and wa[1]["media"]["nom_fichier"] == "papier-entete-A5.pdf" and wa[1]["media"]["contenu_base64"]
    import base64
    pdf = base64.b64encode(b"%PDF-1.4 test").decode()
    assert client.post("/messagerie/envoyer", json={"contact_id": c["id"], "document": {"type": "fichier", "mime": "application/pdf", "nom": "convocation.pdf", "contenu_base64": pdf}}, headers=h).status_code == 200
    assert client.post("/messagerie/envoyer", json={"contact_id": c["id"], "document": {"type": "fichier", "mime": "application/zip", "nom": "x.zip", "contenu_base64": pdf}}, headers=h).status_code == 422
    assert client.post("/messagerie/envoyer", json={"contact_id": c["id"], "texte": ""}, headers=h).status_code == 422                 # rien à envoyer
    # le texte n'est jamais dans le journal
    assert not any("Bonjour" in l.get("detail", "") for l in client.get("/journal", headers=entete(client, "adm")).json())


def test_une_facture_ne_part_qu_au_patient_concerne(client, wa):
    h = entete(client, "sec")
    p = nouveau_patient(client, h)
    c = _contact(client, h, patient_id=p["id"])
    db.base().factures.insert_one({"id": "f1", "numero": "F-1", "patient_id": "un-autre-patient"})
    r = client.post("/messagerie/envoyer", json={"contact_id": c["id"], "document": {"type": "facture", "id": "f1"}}, headers=h)
    assert r.status_code == 400 and not wa                                                                                   # rien n'est parti


def test_whatsapp_non_configure(client, monkeypatch):
    monkeypatch.delenv("LILUVINE_WA_URL", raising=False)
    h = entete(client, "sec")
    c = _contact(client, h)
    assert client.get("/messagerie/etat", headers=h).json()["configure"] is False
    assert client.post("/messagerie/envoyer", json={"contact_id": c["id"], "texte": "Bonjour"}, headers=h).status_code == 503


def test_retour_signe_et_stop(client, wa):
    h = entete(client, "sec")
    c = _contact(client, h)
    assert client.post("/api/webhooks/liluvine-retour", content=b"{}", headers={"X-Timestamp": str(int(time.time())), "X-Signature": "faux"}).status_code == 401
    assert client.post("/api/webhooks/liluvine-retour", content=b"{}", headers={"X-Timestamp": "1", "X-Signature": whatsapp.signer(CLE, "1", "{}")}).status_code == 401   # horodatage périmé
    assert _retour(client, {"type": "desinscription", "de": "+22670123456"}).status_code == 200
    assert client.get("/messagerie/contacts", headers=h).json()[0]["desinscrit"] is True
    assert client.post("/messagerie/envoyer", json={"contact_id": c["id"], "texte": "Bonjour"}, headers=h).status_code == 409 and not wa


def test_reponse_statut_et_reservation(client, wa):
    h = entete(client, "sec")
    c = _contact(client, h)
    client.post("/messagerie/envoyer", json={"contact_id": c["id"], "texte": "Bonjour"}, headers=h)
    mid = client.get(f"/messagerie/contacts/{c['id']}/messages", headers=h).json()["messages"][0]["id"]
    assert _retour(client, {"type": "statut", "id": mid, "statut": "delivered"}).status_code == 200
    assert client.get(f"/messagerie/contacts/{c['id']}/messages", headers=h).json()["messages"][0]["statut"] == "remis"
    assert _retour(client, {"type": "reponse", "de": "+22670123456", "texte": "Je voudrais un rendez-vous la semaine prochaine"}).status_code == 200
    e = client.get("/messagerie/etat", headers=h).json()
    assert e["configure"] is True and e["non_lus"] == 1 and e["demandes_nouvelles"] == 1 and e["canal"] == "partagee"
    d = client.get("/messagerie/demandes?statut=nouvelle", headers=h).json()[0]
    assert d["type"] == "reservation" and d["contact_nom"] == "OUEDRAOGO Awa"
    assert any("bien été reçue" in m["message"] for m in wa[1:])                                                           # accusé de réception automatique
    assert client.put(f"/messagerie/demandes/{d['id']}", json={"statut": "traitee", "note": "RDV pris le 25"}, headers=h).json()["statut"] == "traitee"
    client.get(f"/messagerie/contacts/{c['id']}/messages", headers=h)                                                      # ouvrir la conversation = lire
    assert client.get("/messagerie/etat", headers=h).json()["non_lus"] == 0


def test_rappels_et_confirmation_par_reponse(client, wa):
    h = entete(client, "sec")
    p = nouveau_patient(client, h, telephone="70123456")
    demain = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    db.base().seances.insert_one({"id": "s1", "patient_id": p["id"], "poste_id": "x", "date": demain, "creneau": "matin", "statut": "planifiee"})
    ap = client.get(f"/messagerie/rappels/apercu?date={demain}", headers=h).json()
    assert ap["a_envoyer"] == 1 and ap["sans_numero"] == 0
    r = client.post("/messagerie/rappels", json={"date": demain}, headers=h)
    assert r.status_code == 200 and r.json()["a_envoyer"] == 1
    assert "matin" in wa[0]["message"] and "CONFIRMER" in wa[0]["message"] and "Bonjour" in wa[0]["message"]
    assert db.base().seances.find_one({"id": "s1"}).get("rappel_wa_le")
    # le patient répond « 1 » : séance confirmée ; « 2 » : empêché + demande à traiter
    _retour(client, {"type": "reponse", "de": "+22670123456", "texte": "1"})
    assert db.base().seances.find_one({"id": "s1"})["confirmation_wa"] == "confirmee"
    _retour(client, {"type": "reponse", "de": "+22670123456", "texte": "2"})
    assert db.base().seances.find_one({"id": "s1"})["confirmation_wa"] == "empeche"
    assert client.get("/messagerie/demandes", headers=h).json()[0]["type"] == "empeche"


def test_messagerie_cloisonnee_par_centre(client, wa):
    b, hb = _centre_b(client)
    ha = entete(client, "sec")
    _contact(client, ha)
    assert client.get("/messagerie/contacts", headers=hb).json() == []                                                   # B ne voit pas les contacts de A
    cb = _contact(client, hb)                                                                                             # même numéro, autre centre : autorisé
    # une réponse est rangée dans le centre auquel on a écrit le plus récemment (B)
    client.post("/messagerie/envoyer", json={"contact_id": cb["id"], "texte": "Bonjour"}, headers=hb)
    _retour(client, {"type": "reponse", "de": "+22670123456", "texte": "Merci"})
    assert client.get("/messagerie/etat", headers=hb).json()["non_lus"] == 1 and client.get("/messagerie/etat", headers=ha).json()["non_lus"] == 0


def test_stats_du_jour(client, wa):
    r = _retour(client, {"type": "stats_du_jour"})
    assert r.status_code == 200
    cles = {i["cle"] for i in r.json()["indicateurs"]}
    assert {"centres", "seances", "patients", "wa_envoyes", "wa_recus"} <= cles and r.json()["version"]


def test_modeles_par_defaut(client, wa):
    h = entete(client, "sec")
    noms = {m["nom"] for m in client.get("/messagerie/modeles", headers=h).json()}
    assert {"Rappel de séance", "Confirmation de réservation", "Facture disponible"} <= noms
    m = client.post("/messagerie/modeles", json={"nom": "Fermeture", "texte": "Le centre est fermé le {date}"}, headers=h).json()
    assert client.put(f"/messagerie/modeles/{m['id']}", json={"nom": "Fermeture", "texte": "Fermé"}, headers=h).json()["texte"] == "Fermé"
    assert client.delete(f"/messagerie/modeles/{m['id']}", headers=h).status_code == 200
