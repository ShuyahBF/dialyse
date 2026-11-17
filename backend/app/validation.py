"""Petites fonctions de validation communes (erreur 422 avec un message en français)."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from fastapi import HTTPException


def erreur(message: str):
    raise HTTPException(422, message)


def normaliser(texte: str) -> str:
    """Minuscules sans accents (recherche et doublons)."""
    t = unicodedata.normalize("NFD", str(texte or "").strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def texte(corps: dict, cle: str, libelle: str, obligatoire: bool = False, max_len: int = 200) -> str:
    """Texte nettoyé (espaces) ; obligatoire ou non."""
    v = str(corps.get(cle) or "").strip()
    if obligatoire and not v:
        erreur(f"{libelle} : champ obligatoire")
    if len(v) > max_len:
        erreur(f"{libelle} : {max_len} caractères au plus")
    return v


def choix(corps: dict, cle: str, libelle: str, valeurs, defaut: str | None = None, obligatoire: bool = False) -> str:
    """Valeur d'une liste finie (liste déroulante)."""
    v = str(corps.get(cle) or defaut or "").strip()
    if not v and not obligatoire:
        return ""
    if v not in valeurs:
        erreur(f"{libelle} : valeur non reconnue")
    return v


def nombre(corps: dict, cle: str, libelle: str, mini: float | None = None, maxi: float | None = None):
    """Nombre (ou None si vide) dans une plage plausible."""
    v = corps.get(cle)
    if v is None or v == "":
        return None
    try:
        n = float(str(v).replace(",", "."))
    except ValueError:
        erreur(f"{libelle} : nombre attendu")
    if (mini is not None and n < mini) or (maxi is not None and n > maxi):
        erreur(f"{libelle} : valeur hors plage ({mini} à {maxi})")
    return n


def date_iso(corps: dict, cle: str, libelle: str, obligatoire: bool = False, futur_ok: bool = True) -> str:
    """Date AAAA-MM-JJ."""
    v = str(corps.get(cle) or "").strip()
    if not v:
        if obligatoire:
            erreur(f"{libelle} : date obligatoire")
        return ""
    try:
        d = date.fromisoformat(v)
    except ValueError:
        erreur(f"{libelle} : date invalide (AAAA-MM-JJ)")
    if not futur_ok and d > date.today():
        erreur(f"{libelle} : ne peut pas être dans le futur")
    return v


def heure(corps: dict, cle: str, libelle: str) -> str:
    """Heure HH:MM (ou vide)."""
    v = str(corps.get(cle) or "").strip()
    if v and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
        erreur(f"{libelle} : heure invalide (HH:MM)")
    return v


def age(date_naissance: str) -> int | None:
    try:
        n = date.fromisoformat(date_naissance)
    except (ValueError, TypeError):
        return None
    auj = date.today()
    return auj.year - n.year - ((auj.month, auj.day) < (n.month, n.day))


def horodatage_valide(v: str) -> bool:
    try:
        datetime.fromisoformat(v)
        return True
    except (ValueError, TypeError):
        return False
