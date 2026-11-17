"""Accès biométriques et WhatsApp : vérification du numéro, connexion par code, second facteur, mot de passe oublié,
empreinte d'appareil, clés d'accès (WebAuthn), anti-énumération, essais limités, révocation après changement de mot de passe."""
import time

import pytest

from app import deuxfacteurs, whatsapp
from authentificateur_virtuel import Telephone
from conftest import entete

NUM = "+226 70 12 34 56"
NUM_BRUT = "22670123456"


@pytest.fixture()
def wa(monkeypatch):
    """WhatsApp simulé : aucun message réel ; on capture les codes et liens « envoyés »."""
    envoyes = []
    monkeypatch.setattr(whatsapp, "configure", lambda: True)
    monkeypatch.setattr(whatsapp, "envoyer_code", lambda numero, code, objet: envoyes.append({"numero": numero, "code": code, "objet": objet}) or (True, ""))
    monkeypatch.setattr(whatsapp, "envoyer_lien", lambda numero, lien: envoyes.append({"numero": numero, "lien": lien}) or (True, ""))
    return envoyes


def _verifier_numero(client, wa, login="med", numero=NUM):
    h = entete(client, login)
    assert client.post("/compte/telephone/demande", json={"telephone": numero}, headers=h).status_code == 200
    code = wa[-1]["code"]
    r = client.post("/compte/telephone/verifier", json={"code": code}, headers=h)
    assert r.status_code == 200, r.text
    return h


def test_verification_du_numero(client, wa):
    h = entete(client, "med")
    assert client.get("/compte/acces", headers=h).json()["telephone_verifie"] is False
    assert client.post("/compte/telephone/demande", json={"telephone": "abc"}, headers=h).status_code == 400
    client.post("/compte/telephone/demande", json={"telephone": NUM}, headers=h)
    assert wa[-1]["numero"] == NUM_BRUT and len(wa[-1]["code"]) == 6
    assert client.post("/compte/telephone/verifier", json={"code": "000000"}, headers=h).status_code == 400
    assert client.post("/compte/telephone/verifier", json={"code": wa[-1]["code"]}, headers=h).json()["telephone"] == "+226 ••• •• 56"      # numéro masqué
    etat = client.get("/compte/acces", headers=h).json()
    assert etat["telephone_verifie"] is True and "7012" not in str(etat)
    # un numéro déjà vérifié par un autre compte est refusé
    assert client.post("/compte/telephone/demande", json={"telephone": NUM}, headers=entete(client, "inf")).status_code == 409


def test_whatsapp_non_configure(client, monkeypatch):
    monkeypatch.setattr(whatsapp, "configure", lambda: False)
    assert client.get("/auth/options").json()["whatsapp"] is False
    assert client.post("/auth/otp/demande", json={"telephone": NUM}).status_code == 503
    assert client.post("/compte/telephone/demande", json={"telephone": NUM}, headers=entete(client, "med")).status_code == 503


def test_connexion_par_code_whatsapp(client, wa):
    _verifier_numero(client, wa)
    wa.clear()
    r = client.post("/auth/otp/demande", json={"telephone": NUM})
    assert r.status_code == 200 and wa[-1]["numero"] == NUM_BRUT
    code = wa[-1]["code"]
    ok = client.post("/auth/otp/verifier", json={"telephone": NUM, "code": code})
    assert ok.status_code == 200 and ok.json()["login"] == "med" and ok.json()["jeton"]
    assert client.post("/auth/otp/verifier", json={"telephone": NUM, "code": code}).status_code == 400            # usage unique


def test_pas_d_enumeration(client, wa):
    _verifier_numero(client, wa)
    wa.clear()
    connu = client.post("/auth/otp/demande", json={"telephone": NUM}).json()
    inconnu = client.post("/auth/otp/demande", json={"telephone": "+226 79 99 99 99"}).json()
    assert connu == inconnu and len(wa) == 1                                    # même réponse ; rien d'envoyé à un numéro inconnu
    assert client.post("/auth/oubli", json={"identifiant": "personne"}).json() == client.post("/auth/oubli", json={"identifiant": "med"}).json()
    assert client.post("/auth/otp/verifier", json={"telephone": "+226 79 99 99 99", "code": "123456"}).status_code == 400


def test_essais_limites_et_blocage(client, wa):
    _verifier_numero(client, wa)
    client.post("/auth/otp/demande", json={"telephone": NUM})
    bon = wa[-1]["code"]
    mauvais = "000000" if bon != "000000" else "111111"
    for _ in range(5):
        assert client.post("/auth/otp/verifier", json={"telephone": NUM, "code": mauvais}).status_code in (400, 429)
    # après 5 échecs : le code est annulé ET le compte bloqué un moment (même règle que le mot de passe)
    assert client.post("/auth/otp/verifier", json={"telephone": NUM, "code": bon}).status_code in (400, 429)
    assert client.post("/auth/login", json={"login": "med", "mot_de_passe": "Motdepasse1"}).status_code == 429


def test_limite_de_demandes_par_heure(client, wa):
    _verifier_numero(client, wa)                                                # 1 demande déjà consommée par la vérification du numéro
    wa.clear()
    for _ in range(10):
        client.post("/auth/otp/demande", json={"telephone": NUM})
    assert len(wa) == 4                                                          # 5 par heure et par compte, au total


def test_code_whatsapp_n_ecarte_pas_l_application_d_authentification(client, wa):
    h = _verifier_numero(client, wa)
    prep = client.post("/auth/2fa/preparer", headers=h).json()
    client.post("/auth/2fa/activer", json={"code": deuxfacteurs.code_a(prep["secret"], time.time())}, headers=h)
    wa.clear()
    client.post("/auth/otp/demande", json={"telephone": NUM})
    r = client.post("/auth/otp/verifier", json={"telephone": NUM, "code": wa[-1]["code"]})
    assert r.status_code == 401 and r.json()["detail"] == "CODE_2FA_REQUIS"


def test_second_facteur_par_whatsapp(client, wa):
    h = _verifier_numero(client, wa)
    assert client.put("/compte/otp-wa", json={"actif": True, "mot_de_passe": "faux"}, headers=h).status_code == 400
    assert client.put("/compte/otp-wa", json={"actif": True, "mot_de_passe": "Motdepasse1"}, headers=h).json()["otp_wa_actif"] is True
    wa.clear()
    r = client.post("/auth/login", json={"login": "med", "mot_de_passe": "Motdepasse1"})
    assert r.status_code == 401 and r.json()["detail"] == "CODE_WA_REQUIS" and len(wa) == 1                  # le code est envoyé
    assert client.post("/auth/login", json={"login": "med", "mot_de_passe": "Motdepasse1", "code_2fa": "000000"}).status_code == 401
    ok = client.post("/auth/login", json={"login": "med", "mot_de_passe": "Motdepasse1", "code_2fa": wa[-1]["code"]})
    assert ok.status_code == 200 and ok.json()["jeton"]
    # sans numéro vérifié, impossible d'activer ; retirer le numéro désactive le second facteur
    assert client.put("/compte/otp-wa", json={"actif": True, "mot_de_passe": "Motdepasse1"}, headers=entete(client, "inf")).status_code == 409
    client.delete("/compte/telephone", headers=ok.json() and {"Authorization": "Bearer " + ok.json()["jeton"]})
    assert client.post("/auth/login", json={"login": "med", "mot_de_passe": "Motdepasse1"}).status_code == 200


def test_mot_de_passe_oublie(client, wa):
    _verifier_numero(client, wa)
    wa.clear()
    client.post("/auth/oubli", json={"identifiant": "med"})
    lien = wa[-1]["lien"]
    assert lien.startswith("https://dialyse.test/reinitialiser?jeton=")
    jeton = lien.split("jeton=")[1]
    assert client.post("/auth/reinitialiser", json={"jeton": jeton, "mot_de_passe": "court"}).status_code == 400
    assert client.post("/auth/reinitialiser", json={"jeton": "faux", "mot_de_passe": "Nouveau1234"}).status_code == 400
    assert client.post("/auth/reinitialiser", json={"jeton": jeton, "mot_de_passe": "Nouveau1234"}).status_code == 200
    assert client.post("/auth/reinitialiser", json={"jeton": jeton, "mot_de_passe": "Autre12345"}).status_code == 400          # lien à usage unique
    assert client.post("/auth/login", json={"login": "med", "mot_de_passe": "Nouveau1234"}).status_code == 200
    assert client.post("/auth/login", json={"login": "med", "mot_de_passe": "Motdepasse1"}).status_code == 401


def test_empreinte_d_appareil(client):
    h = entete(client, "med")
    assert client.post("/compte/biometrie/activer", headers=h).status_code == 400                    # appareil non identifié
    app = {"X-Appareil": "tel-123", **h}
    secret = client.post("/compte/biometrie/activer", headers=app).json()["secret"]
    assert client.get("/compte/acces", headers=app).json()["biometrie_appareil"] is True
    assert client.post("/auth/biometrie", json={"login": "med", "secret": secret}, headers={"X-Appareil": "tel-123"}).status_code == 200
    assert client.post("/auth/biometrie", json={"login": "med", "secret": secret}, headers={"X-Appareil": "autre-tel"}).status_code == 401      # autre appareil
    assert client.post("/auth/biometrie", json={"login": "med", "secret": "faux"}, headers={"X-Appareil": "tel-123"}).status_code == 401
    client.delete("/compte/biometrie", headers=app)
    assert client.post("/auth/biometrie", json={"login": "med", "secret": secret}, headers={"X-Appareil": "tel-123"}).status_code == 401


def test_empreinte_vaut_second_facteur(client):
    h = entete(client, "med")
    prep = client.post("/auth/2fa/preparer", headers=h).json()
    client.post("/auth/2fa/activer", json={"code": deuxfacteurs.code_a(prep["secret"], time.time())}, headers=h)
    secret = client.post("/compte/biometrie/activer", headers={"X-Appareil": "tel-1", **h}).json()["secret"]
    assert client.post("/auth/login", json={"login": "med", "mot_de_passe": "Motdepasse1"}).status_code == 401           # mot de passe seul : code demandé
    assert client.post("/auth/biometrie", json={"login": "med", "secret": secret}, headers={"X-Appareil": "tel-1"}).status_code == 200


def test_changement_de_mot_de_passe_revoque_les_empreintes_apres_reinitialisation(client, wa):
    h = _verifier_numero(client, wa)
    secret = client.post("/compte/biometrie/activer", headers={"X-Appareil": "tel-1", **h}).json()["secret"]
    wa.clear()
    client.post("/auth/oubli", json={"identifiant": "med"})
    client.post("/auth/reinitialiser", json={"jeton": wa[-1]["lien"].split("jeton=")[1], "mot_de_passe": "Nouveau1234"})
    assert client.post("/auth/biometrie", json={"login": "med", "secret": secret}, headers={"X-Appareil": "tel-1"}).status_code == 401      # à refaire


# ---------- clés d'accès (WebAuthn) ----------

ORIGINE = "https://dialyse.test"


def _ajouter_cle(client, h, tel, nom="Téléphone de l'infirmière", **plus):
    o = client.post("/auth/passkey/options-enregistrement", headers=h, json={"mot_de_passe": "Motdepasse1"})
    assert o.status_code == 200, o.text
    return client.post("/auth/passkey/enregistrer", headers=h, json={"defi_id": o.json()["defi_id"], "credential": tel.enregistrer(o.json()["options"], **plus), "nom": nom})


def _connexion_cle(client, tel, **plus):
    o = client.post("/auth/passkey/options-connexion").json()
    return client.post("/auth/passkey/connexion", json={"defi_id": o["defi_id"], "credential": tel.signer(o["options"], **plus)})


def test_cles_d_acces_enregistrement_et_connexion(client):
    h = entete(client, "inf")
    tel = Telephone("dialyse.test", ORIGINE)
    assert client.post("/auth/passkey/options-enregistrement", headers=h, json={"mot_de_passe": "faux"}).status_code == 401
    o = client.post("/auth/passkey/options-enregistrement", headers=h, json={"mot_de_passe": "Motdepasse1"}).json()["options"]
    assert o["rp"]["id"] == "dialyse.test" and o["authenticatorSelection"]["userVerification"] == "required"
    assert _ajouter_cle(client, h, tel).json() == {"ok": True, "nom": "Téléphone de l'infirmière"}
    cles = client.get("/auth/passkey", headers=h).json()["cles"]
    assert len(cles) == 1 and "public_key" not in cles[0] and client.get("/compte/acces", headers=h).json()["cles_acces"] == 1
    r = _connexion_cle(client, tel)
    assert r.status_code == 200 and r.json()["login"] == "inf" and r.json()["jeton"]
    assert client.get("/auth/passkey", headers=h).json()["cles"][0]["dernier_usage"]


def test_cle_d_acces_vaut_authentification_forte(client):
    h = entete(client, "med")
    prep = client.post("/auth/2fa/preparer", headers=h).json()
    client.post("/auth/2fa/activer", json={"code": deuxfacteurs.code_a(prep["secret"], time.time())}, headers=h)
    tel = Telephone("dialyse.test", ORIGINE)
    _ajouter_cle(client, h, tel)
    assert client.post("/auth/login", json={"login": "med", "mot_de_passe": "Motdepasse1"}).status_code == 401           # mot de passe : code demandé
    assert _connexion_cle(client, tel).status_code == 200                                                                    # clé d'accès : pas de second code


def test_defi_a_usage_unique_et_site_controle(client):
    h = entete(client, "inf")
    tel = Telephone("dialyse.test", ORIGINE)
    _ajouter_cle(client, h, tel)
    o = client.post("/auth/passkey/options-connexion").json()
    reponse = tel.signer(o["options"])
    assert client.post("/auth/passkey/connexion", json={"defi_id": o["defi_id"], "credential": reponse}).status_code == 200
    assert client.post("/auth/passkey/connexion", json={"defi_id": o["defi_id"], "credential": reponse}).status_code == 400    # rejeu refusé
    assert _connexion_cle(client, tel, origine="https://faux-site.test").status_code == 401                                   # signée pour un autre site (hameçonnage)
    assert _connexion_cle(client, Telephone("dialyse.test", ORIGINE)).status_code == 401                                       # clé inconnue


def test_cle_d_acces_compte_desactive_et_suppression(client):
    h, ha = entete(client, "inf"), entete(client, "adm")
    tel = Telephone("dialyse.test", ORIGINE)
    _ajouter_cle(client, h, tel)
    cid = client.get("/auth/passkey", headers=h).json()["cles"][0]["credential_id"]
    inf = next(c for c in client.get("/utilisateurs", headers=ha).json() if c["login"] == "inf")
    client.put(f"/utilisateurs/{inf['id']}", json={"actif": False}, headers=ha)
    assert _connexion_cle(client, tel).status_code == 401                                                                       # compte désactivé
    client.put(f"/utilisateurs/{inf['id']}", json={"actif": True}, headers=ha)
    assert _connexion_cle(client, tel).status_code == 200
    h = entete(client, "inf")
    assert client.post(f"/auth/passkey/{cid}/supprimer", headers=h, json={"mot_de_passe": "faux"}).status_code == 401
    assert client.post(f"/auth/passkey/{cid}/supprimer", headers=h, json={"mot_de_passe": "Motdepasse1"}).status_code == 200
    assert _connexion_cle(client, tel).status_code == 401


def test_cles_revoquees_apres_reinitialisation_du_mot_de_passe(client, wa):
    h = _verifier_numero(client, wa)
    tel = Telephone("dialyse.test", ORIGINE)
    _ajouter_cle(client, h, tel)
    wa.clear()
    client.post("/auth/oubli", json={"identifiant": "med"})
    client.post("/auth/reinitialiser", json={"jeton": wa[-1]["lien"].split("jeton=")[1], "mot_de_passe": "Nouveau1234"})
    assert _connexion_cle(client, tel).status_code == 401
