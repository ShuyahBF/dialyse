"""Fond de la page d'accueil : droits, contrôle réel du contenu, image réduite, vidéo conservée, lecture partielle, retrait."""
import io

from PIL import Image

from conftest import entete

# Vidéos « factices » mais avec la VRAIE signature de leur format (le serveur lit la signature, pas l'extension)
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64


def png(largeur=3000, hauteur=2000, mode="RGB"):
    """Image PNG de test (grande, pour vérifier la réduction)."""
    tampon = io.BytesIO()
    Image.new(mode, (largeur, hauteur), (200, 30, 30) if mode == "RGB" else (200, 30, 30, 0)).save(tampon, "PNG")
    return tampon.getvalue()


def envoyer(client, h, donnees):
    return client.put("/fond-accueil/media", content=donnees, headers={**h, "Content-Type": "application/octet-stream"})


def test_sans_fond_la_page_publique_le_dit(client):
    assert client.get("/fond-accueil").json()["actif"] is False         # route PUBLIQUE : aucune connexion exigée
    assert client.get("/fond-accueil/media").status_code == 404


def test_seul_le_super_administrateur_modifie(client):
    for login in ("adm", "med", "inf", "sec", "tec"):
        h = entete(client, login)
        assert envoyer(client, h, png(100, 100)).status_code == 403
        assert client.put("/fond-accueil/reglages", json={"voile": 10}, headers=h).status_code == 403
        assert client.delete("/fond-accueil", headers=h).status_code == 403
    assert envoyer(client, {}, png(100, 100)).status_code == 401


def test_image_reduite_et_reencodee_en_jpeg(client):
    h = entete(client, "sa")
    r = envoyer(client, h, png())
    assert r.status_code == 200 and r.json()["type"] == "image" and r.json()["actif"] is True
    media = client.get("/fond-accueil/media")                           # lecture publique
    assert media.headers["content-type"] == "image/jpeg" and media.headers["x-content-type-options"] == "nosniff"
    img = Image.open(io.BytesIO(media.content))
    assert img.format == "JPEG" and max(img.size) <= 1920               # réduite : 3000 → 1920


def test_image_transparente_acceptee(client):
    assert envoyer(client, entete(client, "sa"), png(200, 100, "RGBA")).status_code == 200


def test_contenu_invalide_refuse_quelle_que_soit_l_extension(client):
    h = entete(client, "sa")
    assert envoyer(client, h, b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>").status_code == 422   # SVG : contenu actif
    assert envoyer(client, h, b"GIF89a" + b"\x00" * 50).status_code == 422
    assert envoyer(client, h, b"MZ" + b"\x00" * 200).status_code == 422                                                           # exécutable
    assert envoyer(client, h, b"").status_code == 422
    assert client.get("/fond-accueil").json()["actif"] is False         # rien n'a été enregistré


def test_video_mp4_et_webm_conservees_telles_quelles(client):
    h = entete(client, "sa")
    r = envoyer(client, h, MP4)
    assert r.status_code == 200 and r.json()["type"] == "video"
    assert client.get("/fond-accueil/media").content == MP4 and client.get("/fond-accueil/media").headers["content-type"] == "video/mp4"
    assert envoyer(client, h, WEBM).status_code == 200
    assert client.get("/fond-accueil/media").headers["content-type"] == "video/webm"


def test_limites_de_taille(client):
    h = entete(client, "sa")
    assert envoyer(client, h, MP4 + b"\x00" * (12 * 1024 * 1024)).status_code == 413
    assert envoyer(client, h, b"\x89PNG" + b"\x00" * (8 * 1024 * 1024 + 1)).status_code == 413


def test_lecture_partielle_pour_la_video(client):
    envoyer(client, entete(client, "sa"), MP4)
    r = client.get("/fond-accueil/media", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and r.content == MP4[:10] and r.headers["content-range"] == f"bytes 0-9/{len(MP4)}"
    assert client.get("/fond-accueil/media", headers={"Range": "bytes=-4"}).content == MP4[-4:]
    assert client.get("/fond-accueil/media", headers={"Range": "bytes=9999-"}).status_code == 416


def test_assombrissement_et_version(client):
    h = entete(client, "sa")
    assert client.put("/fond-accueil/reglages", json={"voile": 20}, headers=h).status_code == 422       # rien à régler sans fond
    v1 = envoyer(client, h, png(100, 100)).json()["version"]
    assert client.put("/fond-accueil/reglages", json={"voile": 20}, headers=h).json()["voile"] == 20
    for faux in (-1, 81, "abc", None):
        assert client.put("/fond-accueil/reglages", json={"voile": faux}, headers=h).status_code == 422
    r = envoyer(client, h, png(120, 100)).json()
    assert r["voile"] == 20 and r["version"] != v1                       # nouveau fichier : le réglage reste, l'adresse change (cache)


def test_retrait_et_journal(client):
    h = entete(client, "sa")
    envoyer(client, h, png(100, 100))
    assert client.delete("/fond-accueil", headers=h).json()["actif"] is False
    assert client.get("/fond-accueil/media").status_code == 404
    lignes = client.get("/journal", headers=h)
    assert lignes.status_code == 200
    actions = {l["action"] for l in lignes.json()}
    assert {"fond_accueil_modifie", "fond_accueil_retire"} <= actions        # chaque changement est journalisé (jamais le contenu)
