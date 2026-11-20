"""Ligne WhatsApp dédiée par centre (émetteur et clé propres, repli facultatif, retours signés par la clé du centre)."""
import json
import time

import pytest

from app import db, whatsapp
from conftest import CENTRE, entete, nouveau_patient
from test_messagerie import CLE, _retour, wa  # noqa: F401
from test_multi_centres import _centre_b

CLE_B = "cle-hmac-du-centre-b-123456"


def _retour_avec(client, corps, cle):
    """Retour signé par la clé d'un centre (ligne dédiée) au lieu de la clé partagée."""
    brut = json.dumps(corps, ensure_ascii=False, separators=(",", ":"))
    ts = str(int(time.time()))
    return client.post("/api/webhooks/liluvine-retour", content=brut.encode(), headers={"X-Timestamp": ts, "X-Signature": whatsapp.signer(cle, ts, brut), "Content-Type": "application/json"})


@pytest.fixture()
def wa_entetes(client, monkeypatch):
    """Comme `wa`, mais on garde aussi les EN-TÊTES (émetteur) des envois."""
    monkeypatch.setenv("LILUVINE_WA_URL", "https://sawali.test/liluvine-send")
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    appels = []

    def faux(url, entetes, corps):
        appels.append((entetes, json.loads(corps)))
        return 200, {"ok": True}
    monkeypatch.setattr(whatsapp, "_appel_http", faux)
    return appels


def _activer_ligne_b(client, b, monkeypatch, repli=False):
    hs = entete(client, "sa")
    r = client.put(f"/centres/{b['id']}", json={"wa_emetteur": "dialyse-cmc", "wa_repli": repli}, headers=hs)
    assert r.status_code == 200, r.text
    monkeypatch.setenv("LILUVINE_WA_HMAC_CMC", CLE_B)
    return r.json()


def test_fiche_du_centre_ligne_et_variable(client, monkeypatch):
    b, hb = _centre_b(client)
    hs = entete(client, "sa")
    f = client.put(f"/centres/{b['id']}", json={"wa_emetteur": "Dialyse-CMC"}, headers=hs).json()
    assert f["wa_emetteur"] == "dialyse-cmc" and f["wa_variable"] == "LILUVINE_WA_HMAC_CMC" and f["wa_cle_presente"] is False            # clé pas encore saisie dans Render
    monkeypatch.setenv("LILUVINE_WA_URL", "https://sawali.test/x")
    monkeypatch.setenv("LILUVINE_WA_HMAC_CMC", CLE_B)
    assert client.get(f"/centres/{b['id']}", headers=hs).json()["wa_cle_presente"] is True
    assert client.put(f"/centres/{b['id']}", json={"wa_emetteur": "x"}, headers=hs).status_code == 422                                  # format invalide
    # l'administrateur du centre ne peut PAS changer sa ligne
    client.put("/centre", json={"wa_emetteur": "autre-ligne", "responsable": "Dr A"}, headers=hb)
    assert client.get(f"/centres/{b['id']}", headers=hs).json()["wa_emetteur"] == "dialyse-cmc"


def test_envoi_par_la_ligne_du_centre(client, wa_entetes, monkeypatch):
    b, hb = _centre_b(client)
    _activer_ligne_b(client, b, monkeypatch)
    ha = entete(client, "adm")
    for h in (ha, hb):
        client.post("/messagerie/contacts", json={"nom": "AWA", "numero": "70123456"}, headers=h)
    ca = client.get("/messagerie/contacts", headers=ha).json()[0]
    cb = client.get("/messagerie/contacts", headers=hb).json()[0]
    assert client.get("/messagerie/etat", headers=hb).json()["canal"] == "ligne_centre" and client.get("/messagerie/etat", headers=ha).json()["canal"] == "partagee"
    client.post("/messagerie/envoyer", json={"contact_id": ca["id"], "texte": "du centre principal"}, headers=ha)
    client.post("/messagerie/envoyer", json={"contact_id": cb["id"], "texte": "du centre B"}, headers=hb)
    (e1, c1), (e2, c2) = wa_entetes
    assert e1["X-Emetteur"] == "dialyse" and e2["X-Emetteur"] == "dialyse-cmc"                                                          # chaque centre écrit par SA ligne
    assert e2["X-Signature"] == whatsapp.signer(CLE_B, e2["X-Timestamp"], json.dumps(c2, ensure_ascii=False, separators=(",", ":")))   # signé avec la clé du centre
    assert client.get(f"/messagerie/contacts/{cb['id']}/messages", headers=hb).json()["messages"][0]["canal"] == "ligne_centre"


def test_sans_cle_le_centre_reste_sur_la_ligne_partagee(client, wa_entetes, monkeypatch):
    b, hb = _centre_b(client)
    client.put(f"/centres/{b['id']}", json={"wa_emetteur": "dialyse-cmc"}, headers=entete(client, "sa"))                                 # variable de clé NON saisie
    monkeypatch.delenv("LILUVINE_WA_HMAC_CMC", raising=False)
    c = client.post("/messagerie/contacts", json={"nom": "AWA", "numero": "70123456"}, headers=hb).json()
    client.post("/messagerie/envoyer", json={"contact_id": c["id"], "texte": "Bonjour"}, headers=hb)
    assert wa_entetes[0][0]["X-Emetteur"] == "dialyse"


def test_repli_sur_la_ligne_partagee_seulement_si_demande(client, monkeypatch):
    b, hb = _centre_b(client)
    monkeypatch.setenv("LILUVINE_WA_URL", "https://sawali.test/x")
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    appels = []

    def faux(url, entetes, corps):
        appels.append(entetes["X-Emetteur"])
        return (403, {}) if entetes["X-Emetteur"] == "dialyse-cmc" else (200, {"ok": True})
    monkeypatch.setattr(whatsapp, "_appel_http", faux)
    _activer_ligne_b(client, b, monkeypatch, repli=False)
    ok, erreur = whatsapp.envoyer("70123456", "Bonjour", centre_id=b["id"])
    assert ok is False and "non autorisé" in erreur and appels == ["dialyse-cmc"]                                                       # pas de repli
    appels.clear()
    client.put(f"/centres/{b['id']}", json={"wa_repli": True}, headers=entete(client, "sa"))
    ok, erreur = whatsapp.envoyer("70123456", "Bonjour", centre_id=b["id"])
    assert ok is True and appels == ["dialyse-cmc", "dialyse"]                                                                          # repli sur la ligne partagée
    appels.clear()
    monkeypatch.setattr(whatsapp, "_appel_http", lambda u, e, c: (409, {}))                                                             # désinscrit : jamais de repli
    ok, erreur = whatsapp.envoyer("70123456", "Bonjour", centre_id=b["id"])
    assert ok is False and "désinscrit" in erreur


def test_retour_signe_par_la_cle_du_centre(client, wa_entetes, monkeypatch):
    b, hb = _centre_b(client)
    _activer_ligne_b(client, b, monkeypatch)
    ha = entete(client, "adm")
    # le même patient est contact des DEUX centres : la clé du centre B dit sans ambiguïté que la réponse est pour B
    client.post("/messagerie/contacts", json={"nom": "AWA", "numero": "70123456"}, headers=ha)
    client.post("/messagerie/contacts", json={"nom": "AWA", "numero": "70123456"}, headers=hb)
    ca = client.get("/messagerie/contacts", headers=ha).json()[0]
    client.post("/messagerie/envoyer", json={"contact_id": ca["id"], "texte": "Bonjour"}, headers=ha)                                  # A a écrit en DERNIER (la ligne partagée aurait choisi A)
    assert _retour_avec(client, {"type": "reponse", "de": "+22670123456", "texte": "Merci"}, CLE_B).status_code == 200
    assert client.get("/messagerie/etat", headers=hb).json()["non_lus"] == 1 and client.get("/messagerie/etat", headers=ha).json()["non_lus"] == 0
    # STOP sur la ligne de B : ne désinscrit que B
    _retour_avec(client, {"type": "desinscription", "de": "+22670123456"}, CLE_B)
    assert client.get("/messagerie/contacts", headers=hb).json()[0]["desinscrit"] is True and client.get("/messagerie/contacts", headers=ha).json()[0]["desinscrit"] is False
    # statistiques de CE centre seulement
    s = _retour_avec(client, {"type": "stats_du_jour"}, CLE_B).json()
    assert next(i for i in s["indicateurs"] if i["cle"] == "centres")["valeur"] == 1
    assert next(i for i in _retour(client, {"type": "stats_du_jour"}).json()["indicateurs"] if i["cle"] == "centres")["valeur"] == 2
    # une clé inconnue est refusée
    assert _retour_avec(client, {"type": "stats_du_jour"}, "cle-inconnue-pas-valable-123").status_code == 401


def test_inconnu_sur_la_ligne_d_un_centre_va_a_ce_centre(client, wa_entetes, monkeypatch):
    b, hb = _centre_b(client)
    _activer_ligne_b(client, b, monkeypatch)
    _retour_avec(client, {"type": "reponse", "de": "+22679999999", "texte": "Bonjour"}, CLE_B)
    assert client.get("/messagerie/contacts", headers=hb).json()[0]["nom"] == "Nouveau contact"                                          # rangé chez B, pas « non classé »
    assert client.get("/messagerie/contacts", headers=entete(client, "adm")).json() == []


def test_journal_de_diagnostic_des_retours_sans_texte_ni_numero(client, caplog, monkeypatch):
    """Le journal du serveur note le type, l'état de remise, l'identifiant et la cause : jamais le texte d'un message ni un numéro."""
    import json
    import logging
    import time
    from app import whatsapp
    cle = "cle-partagee-test"
    monkeypatch.setenv("LILUVINE_WA_HMAC", cle)                 # propre à ce test (rien ne fuit vers les autres)
    corps = json.dumps({"type": "statut", "statut": "failed", "id": "wamid.T1", "erreur": "ligne déconnectée", "to": "+22670123456", "message": "texte secret 987654"})
    h = str(int(time.time()))
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        r = client.post("/api/webhooks/liluvine-retour", content=corps.encode(), headers={"X-Timestamp": h, "X-Signature": whatsapp.signer(cle, h, corps), "Content-Type": "application/json"})
    assert r.status_code == 200
    assert "statut=failed" in caplog.text and "wamid.T1" in caplog.text and "ligne déconnectée" in caplog.text and "ligne=partagee" in caplog.text
    assert "22670123456" not in caplog.text and "987654" not in caplog.text and "texte secret" not in caplog.text
