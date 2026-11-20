"""
WhatsApp par la « Transmission WA Universelle » Liluvine (service de SAWALI) : codes de connexion, vérification du numéro, lien « mot de passe oublié ».
Toutes les plateformes du propriétaire passent par la ligne « Liluvine Standard » de SAWALI : aucun jeton Meta n'est saisi ici.

Protocole (le même que ShuyahStore, sawali-bfmobility, auRor…) :
    POST {LILUVINE_WA_URL}                       ex. https://api.sawalismartsystems.com/api/webhook/liluvine-send
    en-têtes  X-Emetteur, X-Timestamp (secondes epoch), X-Signature = hex(HMAC-SHA256(clé, "<horodatage>.<corps brut>"))
    corps     {"id": uuid, "to": "+226…", "message": "…", "source": "Dialyse"}
Délai 15 s ; UN SEUL nouvel essai (même id, nouvelle signature) sur erreur réseau ou réponse 5xx ; jamais de nouvel essai sur 4xx ;
409 = destinataire désinscrit (il a répondu STOP).

Configuration UNIQUEMENT par variables d'environnement (jamais de secret dans le code) :
  LILUVINE_WA_URL       adresse du service SAWALI (vide = WhatsApp non configuré : rien n'est bloqué, les boutons WhatsApp sont masqués)
  LILUVINE_WA_HMAC      clé HMAC de l'émetteur « dialyse » créé dans SAWALI (SECRET, saisi par le propriétaire ; jamais affiché ni journalisé)
  LILUVINE_WA_EMETTEUR  code de l'émetteur dans SAWALI (défaut « dialyse », pas secret)
  INDICATIF_DEFAUT      indicatif ajouté à un numéro local de 8 chiffres (défaut 226 = Burkina Faso)

Le texte des messages (qui contient un code ou un lien) n'est JAMAIS journalisé : seulement sa longueur. Aucune exception ne sort :
chaque fonction renvoie (ok, message_d_erreur_lisible). Appelé en ARRIÈRE-PLAN seulement (règle 7).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
import urllib.error
import urllib.request
import uuid

from .config import env

log = logging.getLogger("dialyse.liluvine")
DELAI_SECONDES = 15
LONGUEUR_MAX = 4096

_ERREURS = {
    400: "Liluvine : requête refusée (données invalides)", 401: "Liluvine : signature refusée (clé HMAC ou émetteur incorrect)",
    403: "Liluvine : émetteur non autorisé", 404: "Liluvine : adresse du service introuvable (LILUVINE_WA_URL)",
    409: "Ce numéro s'est désinscrit des messages WhatsApp (réponse STOP)", 429: "Liluvine : trop de messages, réessayez dans un instant",
}


def configure(centre_id: str | None = None) -> bool:
    """
    Vrai si un envoi WhatsApp est possible : la LIGNE DU CENTRE (émetteur propre + sa clé `LILUVINE_WA_HMAC_<PRÉFIXE>`) si `centre_id` est donné et que le centre en a une,
    sinon la ligne partagée « dialyse » (adresse ET clé saisies dans Render).
    """
    if centre_id and ligne_du_centre(centre_id):
        return True
    return bool(env("LILUVINE_WA_URL").strip() and env("LILUVINE_WA_HMAC").strip())


def variable_cle_centre(prefixe: str) -> str:
    """Nom de la variable Render qui porte la clé HMAC de la ligne d'un centre : LILUVINE_WA_HMAC_<PRÉFIXE> (ex. LILUVINE_WA_HMAC_CMC)."""
    return "LILUVINE_WA_HMAC_" + re.sub(r"[^A-Z0-9]", "", str(prefixe or "").upper())


def ligne_du_centre(centre_id: str | None) -> dict | None:
    """
    LIGNE DÉDIÉE d'un centre (une ligne WhatsApp privée par centre, assignée dans SAWALI à un émetteur propre à ce centre) : {emetteur, cle, repli, centre_id, prefixe}.
    None si le centre n'a pas d'émetteur, ou si la variable de clé n'est pas saisie dans Render (le centre utilise alors la ligne partagée). Jamais d'exception.
    """
    try:
        if not centre_id:
            return None
        from . import db
        c = db.brut().centres.find_one({"id": centre_id}, {"_id": 0, "wa_emetteur": 1, "wa_repli": 1, "prefixe": 1})
        if not c or not c.get("wa_emetteur"):
            return None
        cle = env(variable_cle_centre(c["prefixe"])).strip()
        if not cle or not env("LILUVINE_WA_URL").strip():
            return None
        return {"emetteur": c["wa_emetteur"], "cle": cle, "repli": bool(c.get("wa_repli")), "centre_id": centre_id, "prefixe": c["prefixe"]}
    except Exception:                                          # noqa: BLE001
        return None


def canal_du_centre(centre_id: str | None) -> str:
    """« ligne_centre » (ligne dédiée), « partagee » (ligne Liluvine commune) ou « aucun »."""
    if ligne_du_centre(centre_id):
        return "ligne_centre"
    return "partagee" if configure() else "aucun"


def cles_de_retour() -> list[tuple[str | None, str]]:
    """Clés avec lesquelles SAWALI peut signer un RETOUR : la clé partagée (centre None) puis la clé de chaque centre qui a une ligne dédiée. La clé qui vérifie la signature dit de quel centre vient le retour."""
    res: list[tuple[str | None, str]] = []
    if env("LILUVINE_WA_HMAC").strip():
        res.append((None, env("LILUVINE_WA_HMAC").strip()))
    try:
        from . import db
        for c in db.brut().centres.find({"wa_emetteur": {"$exists": True, "$ne": ""}}, {"_id": 0, "id": 1, "prefixe": 1}):
            cle = env(variable_cle_centre(c["prefixe"])).strip()
            if cle:
                res.append((c["id"], cle))
    except Exception:                                          # noqa: BLE001
        pass
    return res


def normaliser_numero(brut: str) -> str:
    """
    Numéro réduit à ses chiffres, indicatif compris (« +226 70 00 00 00 » → « 22670000000 »).
    Un numéro local de 8 chiffres reçoit l'indicatif par défaut (INDICATIF_DEFAUT). Chaîne vide si invalide (norme E.164 : 10 à 15 chiffres).
    """
    chiffres = re.sub(r"\D", "", str(brut or ""))
    if chiffres.startswith("00"):
        chiffres = chiffres[2:]
    if len(chiffres) == 8:
        chiffres = env("INDICATIF_DEFAUT", "226") + chiffres
    return chiffres if re.fullmatch(r"[1-9]\d{9,14}", chiffres) else ""


def masquer_numero(numero: str) -> str:
    """« 22670123456 » → « +226 ••• •• 56 » (affichage sans révéler le numéro complet)."""
    return f"+{numero[:3]} ••• •• {numero[-2:]}" if len(numero) >= 6 else "••••"


def signer(cle: str, horodatage: str, corps_brut: str) -> str:
    """Signature du protocole : hex(HMAC-SHA256(clé, "<horodatage>.<corps brut>"))."""
    return hmac.new(cle.encode("utf-8"), f"{horodatage}.{corps_brut}".encode("utf-8"), hashlib.sha256).hexdigest()


def _appel_http(url: str, entetes: dict, corps: bytes) -> tuple[int, dict]:
    """Un appel HTTP (état, JSON). Remplacé par les tests : aucun appel réseau réel en test. Lève une OSError sur erreur réseau."""
    req = urllib.request.Request(url, data=corps, headers=entetes, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=DELAI_SECONDES) as r:
            octets, etat = r.read(), r.status
    except urllib.error.HTTPError as e:
        octets, etat = e.read(), e.code
    try:
        return etat, json.loads(octets or b"{}")
    except ValueError:
        return etat, {}


MEDIA_TYPES = ("document", "image")
MEDIA_MAX_OCTETS = 10 * 1024 * 1024          # protocole v3 : 10 Mo au plus (refusé localement, sans appel réseau)


def _champ_media(media: dict) -> dict:
    """Champ « media » du corps signé (protocole v3) : octets encodés en base64. Lève ValueError si le média est invalide."""
    import base64
    genre = str(media.get("type") or "").lower()
    octets = media.get("contenu") or b""
    if genre not in MEDIA_TYPES:
        raise ValueError("Type de média invalide (document ou image)")
    if not octets or len(octets) > MEDIA_MAX_OCTETS:
        raise ValueError("Fichier vide ou de plus de 10 Mo")
    champ = {"type": genre, "contenu_base64": base64.b64encode(octets).decode("ascii")}
    for cle in ("nom_fichier", "mime", "legende"):
        if media.get(cle):
            champ[cle] = str(media[cle])[:200]
    return champ


def _envoyer_via(url: str, emetteur: str, cle: str, destinataire: str, message: str, media: dict | None, identifiant: str | None) -> tuple[bool, str]:
    """Un envoi par UNE ligne (émetteur + clé) : signature, un nouvel essai sur 5xx / réseau, jamais sur 4xx. Rend (ok, erreur lisible)."""
    corps = {"id": identifiant or str(uuid.uuid4()), "to": "+" + destinataire, "message": message[:LONGUEUR_MAX], "source": "Dialyse"}
    if media:
        try:
            corps["media"] = _champ_media(media)
        except ValueError as e:
            return False, str(e)
    brut = json.dumps(corps, ensure_ascii=False, separators=(",", ":"))      # sérialisé UNE fois : ce texte est signé ET envoyé (même id au 2e essai)
    derniere = "Liluvine injoignable"
    for essai in (1, 2):
        horodatage = str(int(time.time()))
        entetes = {"Content-Type": "application/json", "X-Emetteur": emetteur, "X-Timestamp": horodatage, "X-Signature": signer(cle, horodatage, brut)}
        try:
            etat, donnees = _appel_http(url, entetes, brut.encode("utf-8"))
        except OSError as exc:
            log.warning("Liluvine : erreur réseau (essai %s) : %s", essai, type(exc).__name__)
            continue
        if etat >= 500:
            log.warning("Liluvine : HTTP %s (essai %s)", etat, essai)
            derniere = f"Liluvine : erreur du service (HTTP {etat})"
            continue
        if etat == 200:
            return (True, "") if donnees.get("ok", True) else (False, "Liluvine : envoi refusé")
        log.warning("Liluvine : refus HTTP %s (message de %s caractères)", etat, len(message))      # jamais le texte (il contient un code)
        return False, _ERREURS.get(etat, f"Liluvine : refus (HTTP {etat})")
    return False, derniere


def envoyer(numero: str, texte: str, media: dict | None = None, identifiant: str | None = None, centre_id: str | None = None) -> tuple[bool, str]:
    """
    Envoie `texte` au numéro (chiffres, indicatif compris), avec un DOCUMENT ou une IMAGE facultatif (`media` : type, contenu en octets, nom_fichier, mime, legende ; protocole v3).
    `identifiant` : identifiant du message (suivi des statuts de remise par SAWALI). `centre_id` : si le centre a sa LIGNE DÉDIÉE, le message part par elle (émetteur et clé du centre) ;
    en cas d'échec de cette ligne, repli sur la ligne partagée SEULEMENT si le centre l'a demandé (`wa_repli`) et si l'échec ne tient pas au numéro. Ne lève JAMAIS d'exception. Rend (ok, erreur lisible).
    """
    try:
        destinataire = normaliser_numero(numero)
        message = (texte or "").strip()
        ligne = ligne_du_centre(centre_id)
        partagee = bool(env("LILUVINE_WA_URL").strip() and env("LILUVINE_WA_HMAC").strip())
        if not ligne and not partagee:
            return False, "WhatsApp n'est pas configuré sur le serveur (LILUVINE_WA_URL et LILUVINE_WA_HMAC)"
        if not destinataire:
            return False, "Numéro WhatsApp invalide"
        if not message and not media:
            return False, "Message vide"
        url = env("LILUVINE_WA_URL").strip()
        if ligne:
            ok, erreur = _envoyer_via(url, ligne["emetteur"], ligne["cle"], destinataire, message, media, identifiant)
            # repli : jamais si le numéro est en cause (STOP = 409, numéro refusé = 400) ni sans demande du centre
            if ok or not ligne["repli"] or not partagee or "désinscrit" in erreur or "données invalides" in erreur:
                return ok, erreur
            log.warning("Liluvine : ligne du centre en échec, repli sur la ligne partagée")
        return _envoyer_via(url, (env("LILUVINE_WA_EMETTEUR") or "dialyse").strip(), env("LILUVINE_WA_HMAC").strip(), destinataire, message, media, identifiant)
    except Exception as exc:                                     # noqa: BLE001 — un envoi raté ne doit jamais faire tomber une requête
        log.warning("Liluvine : erreur inattendue (%s)", type(exc).__name__)
        return False, "Envoi WhatsApp impossible"


def envoyer_code(numero: str, code: str, objet: str) -> tuple[bool, str]:
    """Code de vérification à 6 chiffres (valable 5 minutes)."""
    return envoyer(numero, f"Dialyse — {objet} : votre code est {code}. Valable 5 minutes. Ne le communiquez à personne.")


def envoyer_lien(numero: str, lien: str) -> tuple[bool, str]:
    """Lien de réinitialisation du mot de passe (valable 30 minutes, usage unique)."""
    return envoyer(numero, f"Dialyse — réinitialisation du mot de passe : {lien} (valable 30 minutes, à usage unique). "
                           "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.")
