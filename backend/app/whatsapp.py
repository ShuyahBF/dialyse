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


def configure() -> bool:
    """Vrai si la Transmission universelle est utilisable (adresse ET clé saisies dans Render)."""
    return bool(env("LILUVINE_WA_URL").strip() and env("LILUVINE_WA_HMAC").strip())


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


def envoyer(numero: str, texte: str) -> tuple[bool, str]:
    """Envoie `texte` au numéro (chiffres, indicatif compris). Ne lève JAMAIS d'exception. Rend (ok, erreur lisible)."""
    try:
        if not configure():
            return False, "WhatsApp n'est pas configuré sur le serveur (LILUVINE_WA_URL et LILUVINE_WA_HMAC)"
        destinataire = normaliser_numero(numero)
        message = (texte or "").strip()
        if not destinataire:
            return False, "Numéro WhatsApp invalide"
        if not message:
            return False, "Message vide"
        corps = {"id": str(uuid.uuid4()), "to": "+" + destinataire, "message": message[:LONGUEUR_MAX], "source": "Dialyse"}
        brut = json.dumps(corps, ensure_ascii=False, separators=(",", ":"))      # sérialisé UNE fois : ce texte est signé ET envoyé (même id au 2e essai)
        derniere = "Liluvine injoignable"
        for essai in (1, 2):
            horodatage = str(int(time.time()))
            entetes = {"Content-Type": "application/json", "X-Emetteur": (env("LILUVINE_WA_EMETTEUR") or "dialyse").strip(),
                       "X-Timestamp": horodatage, "X-Signature": signer(env("LILUVINE_WA_HMAC").strip(), horodatage, brut)}
            try:
                etat, donnees = _appel_http(env("LILUVINE_WA_URL").strip(), entetes, brut.encode("utf-8"))
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
