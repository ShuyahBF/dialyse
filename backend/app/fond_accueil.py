"""
Fond de la page d'accueil (page de connexion) : une IMAGE ou une VIDÉO choisie par le super administrateur dans « Apparence De L'Accueil ».

Principes (règle 21 : sécurité avant tout) :
- Réservé au super administrateur (envoi, réglage, retrait) ; la lecture est PUBLIQUE (la page de connexion s'affiche avant toute connexion) mais ne
  donne que l'image ou la vidéo, jamais une information du système.
- Rien n'est cru sur parole : le TYPE est lu dans le contenu du fichier (Pillow pour une image ; signature « ftyp » MP4 ou « EBML » WebM pour une vidéo), jamais
  sur l'extension ni sur l'en-tête envoyé. Les SVG, GIF et autres formats actifs sont refusés.
- Image : réduite à 1920 px au plus et ré-encodée en JPEG (métadonnées, géolocalisation et contenu actif retirés), 8 Mo au plus avant traitement.
- Vidéo : 12 Mo au plus (MP4 ou WebM), conservée telle quelle (pas de ré-encodage possible ici) ; le navigateur la joue sans son, en boucle.
- Le fichier est servi avec un type FIXE (jamais deviné par le navigateur : `nosniff`) et un cache long, l'adresse portant un numéro de version qui change à chaque envoi.
- Stockage : une seule ligne dans la collection `fond_accueil` (hors sauvegardes chiffrées : un gros fichier multimédia n'a pas à alourdir les copies de sécurité).
- Chaque changement est journalisé (qui, quand, type, taille), jamais le contenu.

Pour un développeur WinDev : c'est l'équivalent d'un champ « image de fond » stocké dans un fichier de paramètres, avec contrôle du contenu avant enregistrement.
"""
from __future__ import annotations

import io
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from . import db, roles, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()

IMAGE_MAX_OCTETS = 8 * 1024 * 1024          # image envoyée (avant réduction)
VIDEO_MAX_OCTETS = 12 * 1024 * 1024         # vidéo (conservée telle quelle ; reste très en dessous des 16 Mo d'un document MongoDB)
IMAGE_COTE_MAX = 1920                       # plus grand côté après réduction
IMAGE_PIXELS_MAX = 40_000_000               # refus des images « bombes » (énormes une fois décompressées)
VOILE_DEFAUT = 45                           # assombrissement (en %) posé sur le fond pour que la carte de connexion reste lisible
ID_DOC = "accueil"


def _collection():
    """Collection globale du fond (non rattachée à un centre : la page de connexion est la même pour tous)."""
    return db.brut().fond_accueil


def _type_video(donnees: bytes) -> str | None:
    """MIME d'une vidéo reconnue d'après son CONTENU (MP4 : « ftyp » aux octets 4 à 8 ; WebM : en-tête EBML), sinon None."""
    if len(donnees) > 12 and donnees[4:8] == b"ftyp":
        return "video/mp4"
    if donnees[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    return None


def _image_vers_jpeg(donnees: bytes) -> bytes:
    """Vérifie RÉELLEMENT l'image avec Pillow (PNG, JPEG ou WebP), la réduit et la ré-encode en JPEG sans métadonnées. Lève 422 si elle est invalide."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(donnees))
        if img.format not in ("PNG", "JPEG", "WEBP"):
            raise ValueError("format")
        largeur, hauteur = img.size
        if largeur * hauteur > IMAGE_PIXELS_MAX:
            raise ValueError("taille")
        img.load()
        if img.mode in ("RGBA", "LA", "P"):                       # transparence : posée sur un fond bleu nuit (jamais de trou dans la page)
            img = img.convert("RGBA")
            fond = Image.new("RGB", img.size, (10, 30, 61))
            fond.paste(img, mask=img.split()[-1])
            img = fond
        else:
            img = img.convert("RGB")
        img.thumbnail((IMAGE_COTE_MAX, IMAGE_COTE_MAX))
        sortie = io.BytesIO()
        img.save(sortie, "JPEG", quality=82, optimize=True, progressive=True)
        return sortie.getvalue()
    except Exception:
        validation.erreur("Image PNG, JPEG ou WebP attendue (8 Mo au plus) ; ou vidéo MP4 / WebM (12 Mo au plus)")


def _public(doc: dict | None) -> dict:
    """Description PUBLIQUE du fond (sans le fichier) : de quoi construire la page de connexion."""
    if not doc:
        return {"actif": False, "type": None, "voile": VOILE_DEFAUT, "version": None, "taille": 0, "modifie_le": None}
    return {"actif": True, "type": doc["type"], "voile": doc.get("voile", VOILE_DEFAUT), "version": doc["version"],
            "taille": doc["taille"], "modifie_le": doc.get("modifie_le")}


@routeur.get("/fond-accueil")
def lire_fond():
    """PUBLIC : le fond actuel de la page d'accueil (type, assombrissement, version). Aucune donnée sensible."""
    return _public(_collection().find_one({"id": ID_DOC}, {"_id": 0, "donnees": 0}))


@routeur.get("/fond-accueil/media")
def lire_media(request: Request):
    """
    PUBLIC : le fichier du fond. Type FIXE (`nosniff`), cache long (l'adresse porte `?v=<version>`), et lecture PARTIELLE (en-tête Range) pour
    que la vidéo démarre vite et se lise sur tous les navigateurs (Safari l'exige).
    """
    doc = _collection().find_one({"id": ID_DOC}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Aucun fond d'accueil")
    donnees = bytes(doc["donnees"])
    total = len(donnees)
    entetes = {"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff", "Accept-Ranges": "bytes",
               "Content-Security-Policy": "default-src 'none'; sandbox", "ETag": f'"{doc["version"]}"'}
    plage = re.fullmatch(r"bytes=(\d*)-(\d*)", (request.headers.get("range") or "").strip())
    if plage and (plage.group(1) or plage.group(2)):
        if plage.group(1):
            debut = int(plage.group(1))
            fin = min(int(plage.group(2)) if plage.group(2) else total - 1, total - 1)
        else:                                                       # « bytes=-500 » : les 500 derniers octets
            debut, fin = max(total - int(plage.group(2)), 0), total - 1
        if debut > fin or debut >= total:
            return Response(status_code=416, headers={**entetes, "Content-Range": f"bytes */{total}"})
        return Response(donnees[debut:fin + 1], status_code=206, media_type=doc["mime"],
                        headers={**entetes, "Content-Range": f"bytes {debut}-{fin}/{total}"})
    return Response(donnees, media_type=doc["mime"], headers=entetes)


@routeur.put("/fond-accueil/media")
async def envoyer_media(request: Request, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """
    Remplace le fond : le CORPS de la requête est le fichier lui-même (octets bruts). Le type est lu dans le contenu ; une image est réduite
    et ré-encodée, une vidéo est contrôlée puis conservée. L'assombrissement déjà réglé est conservé.
    """
    limite = max(IMAGE_MAX_OCTETS, VIDEO_MAX_OCTETS)
    try:
        annonce = int(request.headers.get("content-length") or 0)
    except ValueError:
        annonce = 0
    if annonce > limite:
        raise HTTPException(413, "Fichier trop lourd : image 8 Mo au plus, vidéo 12 Mo au plus")
    corps = await request.body()
    if not corps:
        validation.erreur("Aucun fichier reçu")

    def travail() -> dict:
        mime_video = _type_video(corps)
        if mime_video:
            if len(corps) > VIDEO_MAX_OCTETS:
                raise HTTPException(413, "Vidéo trop lourde : 12 Mo au plus (réduisez-la ou raccourcissez-la)")
            genre, mime, donnees = "video", mime_video, corps
        else:
            if len(corps) > IMAGE_MAX_OCTETS:
                raise HTTPException(413, "Image trop lourde : 8 Mo au plus")
            genre, mime, donnees = "image", "image/jpeg", _image_vers_jpeg(corps)
        ancien = _collection().find_one({"id": ID_DOC}, {"_id": 0, "voile": 1}) or {}
        doc = {"id": ID_DOC, "type": genre, "mime": mime, "donnees": donnees, "taille": len(donnees), "version": uuid.uuid4().hex[:12],
               "voile": ancien.get("voile", VOILE_DEFAUT), "modifie_le": db.maintenant(), "modifie_par": u.get("login")}
        _collection().replace_one({"id": ID_DOC}, doc, upsert=True)
        journaliser("fond_accueil_modifie", u, f"{genre} {len(donnees) // 1024} Ko")
        return _public(doc)
    return await run_in_threadpool(travail)


@routeur.put("/fond-accueil/reglages")
def regler_fond(corps: dict, u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Règle l'assombrissement (0 à 80 %) posé sur le fond pour garder la carte de connexion lisible."""
    try:
        voile = int(corps.get("voile"))
    except (TypeError, ValueError):
        validation.erreur("Assombrissement : un nombre entre 0 et 80")
    if not 0 <= voile <= 80:
        validation.erreur("Assombrissement : un nombre entre 0 et 80")
    if not _collection().find_one({"id": ID_DOC}, {"_id": 1}):
        validation.erreur("Choisissez d'abord une image ou une vidéo")
    _collection().update_one({"id": ID_DOC}, {"$set": {"voile": voile, "modifie_le": db.maintenant(), "modifie_par": u.get("login")}})
    journaliser("fond_accueil_regle", u, f"assombrissement {voile} %")
    return _public(_collection().find_one({"id": ID_DOC}, {"_id": 0, "donnees": 0}))


@routeur.delete("/fond-accueil")
def retirer_fond(u: dict = Depends(exiger_roles(roles.SUPER_ADMIN))):
    """Retire le fond : la page de connexion retrouve son fond bleu nuit habituel."""
    _collection().delete_one({"id": ID_DOC})
    journaliser("fond_accueil_retire", u, "")
    return _public(None)
