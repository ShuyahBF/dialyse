"""WhatsApp par la Transmission universelle Liluvine de SAWALI : signature, en-têtes, nouvel essai, refus, désinscription, secret jamais journalisé."""
import json
import logging

import pytest

from app import whatsapp


@pytest.fixture()
def reseau(monkeypatch):
    """Serveur Liluvine SIMULÉ : garde les appels reçus ; `reponses` = suite d'états à renvoyer (ou d'exceptions réseau)."""
    appels, reponses = [], []

    def faux(url, entetes, corps):
        appels.append({"url": url, "entetes": entetes, "corps": corps})
        r = reponses.pop(0) if reponses else (200, {"ok": True})
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(whatsapp, "_appel_http", faux)
    monkeypatch.setenv("LILUVINE_WA_URL", "https://sawali.test/api/webhook/liluvine-send")
    monkeypatch.setenv("LILUVINE_WA_HMAC", "cle-secrete-de-test")
    monkeypatch.setenv("LILUVINE_WA_EMETTEUR", "dialyse")
    return appels, reponses


def test_configuration(monkeypatch):
    monkeypatch.delenv("LILUVINE_WA_URL", raising=False)
    monkeypatch.delenv("LILUVINE_WA_HMAC", raising=False)
    assert whatsapp.configure() is False
    assert whatsapp.envoyer("22670123456", "x") == (False, "WhatsApp n'est pas configuré sur le serveur (LILUVINE_WA_URL et LILUVINE_WA_HMAC)")
    monkeypatch.setenv("LILUVINE_WA_URL", "https://sawali.test/x")
    assert whatsapp.configure() is False                                    # l'adresse seule ne suffit pas : la clé est exigée
    monkeypatch.setenv("LILUVINE_WA_HMAC", "k")
    assert whatsapp.configure() is True


def test_numeros():
    assert whatsapp.normaliser_numero("+226 70 12 34 56") == "22670123456"
    assert whatsapp.normaliser_numero("0022670123456") == "22670123456"
    assert whatsapp.normaliser_numero("70123456") == "22670123456"            # numéro local : indicatif par défaut
    assert whatsapp.normaliser_numero("123") == "" and whatsapp.normaliser_numero("abc") == "" and whatsapp.normaliser_numero(None) == ""
    assert whatsapp.masquer_numero("22670123456") == "+226 ••• •• 56"


def test_signature_et_en_tetes_du_protocole(reseau):
    appels, _ = reseau
    assert whatsapp.envoyer_code("22670123456", "482913", "connexion") == (True, "")
    a = appels[0]
    assert a["url"] == "https://sawali.test/api/webhook/liluvine-send"
    e = a["entetes"]
    assert e["X-Emetteur"] == "dialyse" and e["Content-Type"] == "application/json"
    # la signature est celle du protocole : HMAC-SHA256(clé, "<horodatage>.<corps brut>")
    assert e["X-Signature"] == whatsapp.signer("cle-secrete-de-test", e["X-Timestamp"], a["corps"].decode())
    corps = json.loads(a["corps"])
    assert corps["to"] == "+22670123456" and corps["source"] == "Dialyse" and "482913" in corps["message"] and len(corps["id"]) == 36
    assert "cle-secrete-de-test" not in a["corps"].decode()                   # la clé ne part jamais dans le corps
    assert whatsapp.signer("autre", e["X-Timestamp"], a["corps"].decode()) != e["X-Signature"]


def test_un_seul_nouvel_essai_sur_5xx_avec_le_meme_id(reseau):
    appels, reponses = reseau
    reponses += [(503, {}), (200, {"ok": True})]
    assert whatsapp.envoyer("22670123456", "bonjour")[0] is True
    assert len(appels) == 2 and json.loads(appels[0]["corps"])["id"] == json.loads(appels[1]["corps"])["id"]      # idempotence côté SAWALI
    appels.clear()
    reponses += [OSError("réseau"), OSError("réseau")]
    ok, erreur = whatsapp.envoyer("22670123456", "bonjour")
    assert ok is False and len(appels) == 2 and "injoignable" in erreur           # jamais plus de 2 essais
    appels.clear()
    reponses += [(500, {}), (502, {})]
    assert whatsapp.envoyer("22670123456", "bonjour") == (False, "Liluvine : erreur du service (HTTP 502)")


@pytest.mark.parametrize("etat,attendu", [(401, "signature refusée"), (403, "émetteur non autorisé"), (404, "introuvable"), (429, "trop de messages"), (400, "invalides"), (418, "HTTP 418")])
def test_aucun_nouvel_essai_sur_4xx(reseau, etat, attendu):
    appels, reponses = reseau
    reponses.append((etat, {}))
    ok, erreur = whatsapp.envoyer("22670123456", "x")
    assert ok is False and attendu in erreur and len(appels) == 1


def test_desinscription_stop(reseau):
    appels, reponses = reseau
    reponses.append((409, {}))
    ok, erreur = whatsapp.envoyer("22670123456", "x")
    assert ok is False and "désinscrit" in erreur and len(appels) == 1


def test_refus_applicatif_et_entrees_invalides(reseau):
    appels, reponses = reseau
    reponses.append((200, {"ok": False}))
    assert whatsapp.envoyer("22670123456", "x") == (False, "Liluvine : envoi refusé")
    appels.clear()
    assert whatsapp.envoyer("abc", "x") == (False, "Numéro WhatsApp invalide")
    assert whatsapp.envoyer("22670123456", "   ") == (False, "Message vide")
    assert appels == []                                                       # refusé localement, sans aucun appel


def test_le_texte_et_la_cle_ne_sont_jamais_journalises(reseau, caplog):
    appels, reponses = reseau
    reponses += [(503, {}), (401, {})]
    with caplog.at_level(logging.DEBUG, logger="dialyse.liluvine"):
        whatsapp.envoyer_code("22670123456", "482913", "connexion")
    journal = caplog.text
    assert "482913" not in journal and "cle-secrete-de-test" not in journal and "22670123456" not in journal
    assert "caractères" in journal                                            # seule la longueur est notée


def test_jamais_d_exception(monkeypatch):
    monkeypatch.setenv("LILUVINE_WA_URL", "https://sawali.test/x")
    monkeypatch.setenv("LILUVINE_WA_HMAC", "k")
    monkeypatch.setattr(whatsapp, "_appel_http", lambda *a: (_ for _ in ()).throw(ValueError("bug")))
    assert whatsapp.envoyer("22670123456", "x") == (False, "Envoi WhatsApp impossible")
