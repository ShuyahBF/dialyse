"""
Envoi de messages WhatsApp par l'API WhatsApp Cloud de Meta (même principe que SAWALI / e-Kol).
Configuration UNIQUEMENT par variables d'environnement (jamais de secret dans le code) :

  WHATSAPP_ACCESS_TOKEN       jeton d'accès permanent de l'API WhatsApp Cloud (secret)
  WHATSAPP_PHONE_NUMBER_ID    identifiant du numéro émetteur
  WHATSAPP_OTP_TEMPLATE       nom du modèle approuvé « code de vérification » (1 paramètre : le code) — recommandé
  WHATSAPP_RESET_TEMPLATE     nom du modèle approuvé « lien de réinitialisation » (catégorie Utility, 1 paramètre : le lien) — recommandé
  WHATSAPP_TEMPLATE_LANG      langue des modèles (défaut « fr »)

Sans modèle approuvé, WhatsApp n'accepte un message libre que si la personne a écrit au numéro dans les dernières 24 h :
le message texte reste donc tenté en dernier recours. Chaque fonction renvoie (ok, message_d_erreur_lisible).
"""
from __future__ import annotations

import json
import re
import urllib.request

from .config import env

URL_GRAPH = "https://graph.facebook.com/v21.0/{numero}/messages"


def configure() -> bool:
    """Vrai si le serveur sait envoyer des messages WhatsApp (jeton ET numéro émetteur présents)."""
    return bool(env("WHATSAPP_ACCESS_TOKEN") and env("WHATSAPP_PHONE_NUMBER_ID"))


def normaliser_numero(brut: str) -> str:
    """
    Numéro réduit à ses chiffres, indicatif compris (« +226 70 00 00 00 » → « 22670000000 »).
    Un numéro local de 8 chiffres reçoit l'indicatif par défaut (INDICATIF_DEFAUT, 226 = Burkina Faso). Chaîne vide si invalide.
    """
    chiffres = re.sub(r"\D", "", str(brut or ""))
    if chiffres.startswith("00"):
        chiffres = chiffres[2:]
    if len(chiffres) == 8:
        chiffres = env("INDICATIF_DEFAUT", "226") + chiffres
    return chiffres if 10 <= len(chiffres) <= 15 else ""


def masquer_numero(numero: str) -> str:
    """« 22670123456 » → « +226 ••• •• 56 » (affichage sans révéler le numéro complet)."""
    return f"+{numero[:3]} ••• •• {numero[-2:]}" if len(numero) >= 6 else "••••"


def _poster(charge: dict) -> tuple[bool, str]:
    """Un appel à l'API Meta ; (ok, détail d'erreur). Appelé en ARRIÈRE-PLAN seulement (règle 7)."""
    url = URL_GRAPH.format(numero=env("WHATSAPP_PHONE_NUMBER_ID"))
    req = urllib.request.Request(url, data=json.dumps(charge).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + env("WHATSAPP_ACCESS_TOKEN"), "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return True, ""
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.read()[:200].decode(errors='replace')}"
    except Exception as e:                                  # réseau, délai…
        return False, type(e).__name__


def envoyer(numero: str, texte: str, modele: str = "", parametre: str = "") -> tuple[bool, str]:
    """
    Envoie `texte` à `numero`. Si `modele` est donné, le modèle approuvé est tenté d'abord (corps = `parametre`),
    puis le message texte libre en dernier recours.
    """
    if not configure():
        return False, "WhatsApp n'est pas configuré sur le serveur"
    erreurs = []
    langue = env("WHATSAPP_TEMPLATE_LANG", "fr")
    if modele:
        corps = {"type": "body", "parameters": [{"type": "text", "text": parametre}]}
        for categorie in ("authentication", "utility"):
            composants = [corps]
            if categorie == "authentication":              # modèle « Authentication » : le bouton « copier le code » reçoit aussi le code
                composants.append({"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": parametre}]})
            ok, detail = _poster({"messaging_product": "whatsapp", "to": numero, "type": "template",
                                  "template": {"name": modele, "language": {"code": langue}, "components": composants}})
            if ok:
                return True, ""
            erreurs.append(detail)
    ok, detail = _poster({"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texte}})
    if ok:
        return True, ""
    print("[whatsapp] échec d'envoi vers", numero[:5] + "…", "|".join(erreurs + [detail]))     # jamais le code ni le lien
    return False, "Envoi WhatsApp impossible"


def envoyer_code(numero: str, code: str, objet: str) -> tuple[bool, str]:
    """Code de vérification à 6 chiffres (valable 5 minutes)."""
    return envoyer(numero, f"Dialyse — {objet} : votre code est {code}. Valable 5 minutes. Ne le communiquez à personne.",
                   env("WHATSAPP_OTP_TEMPLATE"), code)


def envoyer_lien(numero: str, lien: str) -> tuple[bool, str]:
    """Lien de réinitialisation du mot de passe (valable 30 minutes, usage unique)."""
    return envoyer(numero, f"Dialyse — réinitialisation du mot de passe : {lien} (valable 30 minutes, à usage unique). "
                           "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.", env("WHATSAPP_RESET_TEMPLATE"), lien)
