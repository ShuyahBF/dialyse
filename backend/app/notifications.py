"""
Pastilles de notifications du menu (règle du propriétaire, 19/11/2026) : chaque lien de menu qui reçoit des notifications affiche le NOMBRE d'éléments non encore traités.
Une seule route légère pour tout le menu (`GET /notifications/compteurs`), sans appel externe, calculée pour le centre de travail ET pour le rôle (on ne compte jamais ce
que le rôle n'a pas le droit de voir). Les calculs lourds (alertes cliniques) sont gardés 60 secondes par centre (règle 7).
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from . import anonyme, aujourdhui, db, roles
from .auth import utilisateur_courant
from .messagerie import MESSAGERIE
from .stock import statut_stock

routeur = APIRouter()
_cache: dict = {}                 # (centre, clé) → (heure, valeur)
DUREE_CACHE_S = 60


def _en_cache(cle: str, calcul) -> int:
    """Valeur gardée DUREE_CACHE_S secondes pour le centre courant."""
    k = (db.centre_courant.get(), cle)
    hit = _cache.get(k)
    if hit and time.time() - hit[0] < DUREE_CACHE_S:
        return hit[1]
    v = calcul()
    _cache[k] = (time.time(), v)
    return v


@routeur.get("/notifications/compteurs")
def compteurs(u: dict = Depends(utilisateur_courant)) -> dict:
    """Nombre d'éléments à traiter par entrée de menu (clé = chemin du menu). Absent = rien à signaler ou pas de droit."""
    if not u["centre_id"]:
        return {}                                              # compte du groupe sans centre choisi : rien à compter
    b, r = db.base(), u["role"]
    res: dict = {}
    if r in MESSAGERIE:
        res["/messagerie"] = b.wa_messages.count_documents({"sens": "entrant", "lu": False})
        res["/reservations"] = b.wa_demandes.count_documents({"statut": "nouvelle"}) + b.reservations.count_documents({"statut": "demandee"})
    if r in roles.LECTURE_SEANCE:
        res["/aujourdhui"] = aujourdhui.nombre_en_retard()          # séances en retard à démarrer
    if r in anonyme.ROLES_SUIVI:
        res["/suivi"] = _en_cache("alertes", lambda: anonyme.construire()["critiques"])
    if r in roles.LECTURE_STOCK:
        res["/stock"] = _en_cache("stock", lambda: sum(1 for a in b.articles.find({"actif": True}, {"_id": 0, "stock": 1, "seuil_alerte": 1, "par_seance": 1})
                                                       if statut_stock(a.get("stock", 0), a.get("seuil_alerte", 0)) == "rupture" and (a.get("seuil_alerte", 0) > 0 or a.get("par_seance", 0) > 0)))
    return {k: v for k, v in res.items() if v}
