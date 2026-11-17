"""
Consommables et stocks : catalogue d'articles, lots (numéro, péremption), entrées, sorties, pertes, ajustements d'inventaire,
alertes (rupture, seuil bas, péremption) et TRAÇABILITÉ des lots utilisés pour chaque séance (rappel de lot : quels patients ?).

Principes :
  - le stock d'un article est la somme des quantités restantes de ses LOTS (champ `stock` recalculé après chaque opération) ;
  - les sorties suivent la règle « premier périmé, premier sorti » (FEFO) et ignorent les lots périmés ;
  - le démarrage d'une séance consomme automatiquement les articles « par séance » (dialyseur, ligne, aiguilles…) ;
    un stock insuffisant n'empêche JAMAIS un soin : le manque est noté sur la séance et signalé dans les alertes.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from . import db, roles, validation
from .auth import exiger_roles, journaliser

routeur = APIRouter()

CATEGORIES = ["Dialyseur", "Lignes à sang", "Aiguilles et cathéters", "Concentrés et solutions de dialyse", "Sérum et solutions injectables",
              "Médicaments (héparine, fer, EPO…)", "Désinfectants et nettoyage", "Compresses et pansements", "Gants et protections", "Autre"]
UNITES = ["pièce", "boîte", "flacon", "poche", "bidon", "litre", "paire"]
JOURS_PEREMPTION_PROCHE = 60
FIN_DES_TEMPS = "9999-12-31"


def statut_stock(stock: float, seuil: float) -> str:
    """'rupture' (0), 'bas' (≤ seuil) ou 'ok'. Fonction pure."""
    if stock <= 0:
        return "rupture"
    return "bas" if stock <= seuil else "ok"


def statut_peremption(peremption: str, aujourdhui: date | None = None) -> str:
    """'perime', 'bientot' (≤ 60 jours) ou 'ok' ; 'ok' si le lot n'a pas de date. Fonction pure."""
    if not peremption:
        return "ok"
    ref = aujourdhui or date.today()
    if peremption < ref.isoformat():
        return "perime"
    return "bientot" if peremption <= (ref + timedelta(days=JOURS_PEREMPTION_PROCHE)).isoformat() else "ok"


def _article(aid: str) -> dict:
    a = db.base().articles.find_one({"id": aid})
    if not a:
        raise HTTPException(404, "Article introuvable")
    return a


def _recalculer(aid: str) -> float:
    """Stock de l'article = somme des quantités restantes de ses lots (valeur gardée sur l'article pour les listes rapides)."""
    total = sum(l["quantite_restante"] for l in db.base().lots.find({"article_id": aid}, {"quantite_restante": 1}))
    db.base().articles.update_one({"id": aid}, {"$set": {"stock": total}})
    return total


def _prelever(aid: str, quantite: float, numero_lot: str = "", inclure_perimes: bool = False) -> list[dict]:
    """
    Retire `quantite` de l'article : d'un lot précis, ou selon FEFO sur les lots non périmés. Renvoie [{numero, quantite}].
    409 si le stock disponible est insuffisant (rien n'est retiré dans ce cas).
    """
    f: dict = {"article_id": aid, "quantite_restante": {"$gt": 0}}
    if numero_lot:
        f["numero"] = numero_lot
    lots = list(db.base().lots.find(f))
    if not inclure_perimes and not numero_lot:
        lots = [l for l in lots if statut_peremption(l.get("peremption", "")) != "perime"]
    lots.sort(key=lambda l: l.get("peremption") or FIN_DES_TEMPS)
    if sum(l["quantite_restante"] for l in lots) < quantite:
        raise HTTPException(409, "Stock insuffisant" + (" dans ce lot" if numero_lot else " (hors lots périmés)"))
    reste, pris = quantite, []
    for l in lots:
        if reste <= 0:
            break
        q = min(reste, l["quantite_restante"])
        db.base().lots.update_one({"id": l["id"]}, {"$set": {"quantite_restante": l["quantite_restante"] - q}})
        pris.append({"numero": l["numero"], "quantite": q})
        reste -= q
    return pris


def _mouvement(a: dict, type_: str, delta: float, u: dict, **extra) -> dict:
    m = {"id": str(uuid.uuid4()), "article_id": a["id"], "article": a["nom"], "type": type_, "delta": delta, "quand": db.maintenant(),
         "date": extra.pop("date", "") or db.maintenant()[:10], "par": u.get("login", ""), **extra}
    db.base().mouvements.insert_one(m)
    return m


def consommer_seance(seance_id: str, patient_id: str, u: dict) -> tuple[list[dict], list[str]]:
    """
    Consomme les articles « par séance » (FEFO) et enregistre les lots utilisés (traçabilité).
    Renvoie (consommables [{article_id, nom, quantite, lots}], manques [noms]). Ne lève jamais d'erreur de stock.
    """
    faits, manques = [], []
    for a in db.base().articles.find({"actif": True, "par_seance": {"$gt": 0}}).sort("nom", 1):
        try:
            lots = _prelever(a["id"], a["par_seance"])
        except HTTPException:
            manques.append(a["nom"])
            continue
        _recalculer(a["id"])
        _mouvement(a, "sortie", -a["par_seance"], u, motif="Séance", seance_id=seance_id, patient_id=patient_id, lots=lots)
        faits.append({"article_id": a["id"], "nom": a["nom"], "quantite": a["par_seance"], "lots": lots})
    return faits, manques


def _public(a: dict) -> dict:
    d = {k: v for k, v in a.items() if k != "_id"}
    d["statut_stock"] = statut_stock(a.get("stock", 0), a.get("seuil_alerte", 0))
    return d


@routeur.get("/stock/listes")
def listes(u: dict = Depends(exiger_roles(roles.LECTURE_STOCK))):
    return {"categories": CATEGORIES, "unites": UNITES, "jours_peremption_proche": JOURS_PEREMPTION_PROCHE}


@routeur.get("/stock/articles")
def lister(u: dict = Depends(exiger_roles(roles.LECTURE_STOCK))):
    """Articles avec stock, état (rupture / bas / ok) et prochaine péremption (lots lus EN BLOC : règle 7)."""
    articles = list(db.base().articles.find({}, {"_id": 0}).sort("nom", 1))
    prochaines: dict = {}
    for l in db.base().lots.find({"quantite_restante": {"$gt": 0}}, {"_id": 0, "article_id": 1, "peremption": 1}):
        if l.get("peremption"):
            prochaines[l["article_id"]] = min(prochaines.get(l["article_id"], FIN_DES_TEMPS), l["peremption"])
    res = []
    for a in articles:
        d = _public(a)
        d["prochaine_peremption"] = prochaines.get(a["id"], "")
        d["statut_peremption"] = statut_peremption(d["prochaine_peremption"])
        res.append(d)
    return res


def _valider_article(corps: dict, creation: bool) -> dict:
    d: dict = {}
    if creation or "nom" in corps:
        d["nom"] = validation.texte(corps, "nom", "Nom de l'article", True, 100)
    if creation or "categorie" in corps:
        d["categorie"] = validation.choix(corps, "categorie", "Catégorie", CATEGORIES, obligatoire=True)
    if creation or "unite" in corps:
        d["unite"] = validation.choix(corps, "unite", "Unité", UNITES, obligatoire=True)
    if "seuil_alerte" in corps or creation:
        d["seuil_alerte"] = validation.nombre(corps, "seuil_alerte", "Seuil d'alerte", 0, 1000000) or 0
    if "par_seance" in corps or creation:
        d["par_seance"] = validation.nombre(corps, "par_seance", "Quantité par séance", 0, 1000) or 0
    if "actif" in corps:
        d["actif"] = bool(corps["actif"])
    return d


@routeur.post("/stock/articles")
def creer(corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_STOCK))):
    """Crée un article (nom unique) ; code ART-001, ART-002…"""
    d = _valider_article(corps, True)
    if db.base().articles.find_one({"nom": d["nom"]}):
        raise HTTPException(409, "Un article porte déjà ce nom")
    from pymongo import ReturnDocument
    n = db.base().parametres.find_one_and_update({"id": "compteur_articles"}, {"$inc": {"n": 1}}, upsert=True, return_document=ReturnDocument.AFTER)["n"]
    doc = {"id": str(uuid.uuid4()), "code": f"ART-{int(n):03d}", **d, "stock": 0, "actif": True, "created_at": db.maintenant(), "cree_par": u["login"]}
    db.base().articles.insert_one(doc)
    journaliser("article_cree", u, doc["code"])
    return _public(doc)


@routeur.put("/stock/articles/{aid}")
def modifier(aid: str, corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_STOCK))):
    a = _article(aid)
    maj = _valider_article(corps, False)
    if "nom" in maj and maj["nom"] != a["nom"] and db.base().articles.find_one({"nom": maj["nom"]}):
        raise HTTPException(409, "Un article porte déjà ce nom")
    if maj:
        db.base().articles.update_one({"id": aid}, {"$set": maj})
        journaliser("article_modifie", u, f"{a['code']} : {', '.join(sorted(maj))}")
    return _public(db.base().articles.find_one({"id": aid}))


@routeur.delete("/stock/articles/{aid}")
def supprimer(aid: str, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Supprime un article SANS mouvement ; sinon le désactiver."""
    a = _article(aid)
    if db.base().mouvements.find_one({"article_id": aid}):
        raise HTTPException(409, "Cet article a des mouvements : désactivez-le au lieu de le supprimer")
    db.base().articles.delete_one({"id": aid})
    journaliser("article_supprime", u, a["code"])
    return {"ok": True}


@routeur.post("/stock/entrees")
def entree(corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_STOCK))):
    """Réception : quantité, numéro de lot (obligatoire : traçabilité), péremption, fournisseur. Un lot existant est complété."""
    a = _article(str(corps.get("article_id", "")))
    q = validation.nombre(corps, "quantite", "Quantité", 0.0001, 1000000)
    if q is None:
        validation.erreur("Quantité : champ obligatoire")
    numero = validation.texte(corps, "lot", "Numéro de lot", True, 60)
    per = validation.date_iso(corps, "peremption", "Péremption")
    lot = db.base().lots.find_one({"article_id": a["id"], "numero": numero})
    if lot:
        if per and lot.get("peremption") and per != lot["peremption"]:
            raise HTTPException(409, "Ce numéro de lot existe déjà avec une autre date de péremption")
        db.base().lots.update_one({"id": lot["id"]}, {"$set": {"quantite_restante": lot["quantite_restante"] + q, "peremption": lot.get("peremption") or per}})
    else:
        db.base().lots.insert_one({"id": str(uuid.uuid4()), "article_id": a["id"], "numero": numero, "peremption": per, "quantite_restante": q,
                                   "recu_le": db.maintenant()[:10]})
    _recalculer(a["id"])
    m = _mouvement(a, "entree", q, u, lots=[{"numero": numero, "quantite": q}], fournisseur=validation.texte(corps, "fournisseur", "Fournisseur", False, 100),
                   motif="Réception", date=validation.date_iso(corps, "date", "Date de réception", False, futur_ok=False))
    journaliser("stock_entree", u, f"{a['code']} +{q:g} lot {numero}")
    return {k: v for k, v in m.items() if k != "_id"}


@routeur.post("/stock/sorties")
def sortie(corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_STOCK))):
    """Sortie manuelle ou perte (casse, péremption…). Sans lot précisé : FEFO hors périmés ; avec un lot : ce lot (même périmé, pour le sortir du stock)."""
    a = _article(str(corps.get("article_id", "")))
    q = validation.nombre(corps, "quantite", "Quantité", 0.0001, 1000000)
    if q is None:
        validation.erreur("Quantité : champ obligatoire")
    type_ = validation.choix(corps, "type", "Type", ["sortie", "perte"], defaut="sortie")
    motif = validation.texte(corps, "motif", "Motif", type_ == "perte", 200)
    lots = _prelever(a["id"], q, validation.texte(corps, "lot", "Lot", False, 60))
    _recalculer(a["id"])
    m = _mouvement(a, type_, -q, u, motif=motif or "Sortie", lots=lots)
    journaliser("stock_" + type_, u, f"{a['code']} -{q:g}")
    return {k: v for k, v in m.items() if k != "_id"}


@routeur.post("/stock/ajustements")
def ajuster(corps: dict, u: dict = Depends(exiger_roles(roles.ECRITURE_STOCK))):
    """Inventaire : la quantité CONSTATÉE d'un lot remplace la quantité calculée ; l'écart est enregistré avec son motif (obligatoire)."""
    a = _article(str(corps.get("article_id", "")))
    numero = validation.texte(corps, "lot", "Numéro de lot", True, 60)
    constate = validation.nombre(corps, "quantite_constatee", "Quantité constatée", 0, 1000000)
    if constate is None:
        validation.erreur("Quantité constatée : champ obligatoire")
    motif = validation.texte(corps, "motif", "Motif de l'écart", True, 200)
    lot = db.base().lots.find_one({"article_id": a["id"], "numero": numero})
    if not lot:
        raise HTTPException(404, "Lot introuvable pour cet article")
    ecart = constate - lot["quantite_restante"]
    db.base().lots.update_one({"id": lot["id"]}, {"$set": {"quantite_restante": constate}})
    _recalculer(a["id"])
    m = _mouvement(a, "ajustement", ecart, u, motif=motif, lots=[{"numero": numero, "quantite": ecart}])
    journaliser("stock_ajustement", u, f"{a['code']} lot {numero} : {ecart:+g}")
    return {k: v for k, v in m.items() if k != "_id"}


@routeur.get("/stock/articles/{aid}/lots")
def lots(aid: str, u: dict = Depends(exiger_roles(roles.LECTURE_STOCK))):
    """Lots d'un article (avec état de péremption) et 50 derniers mouvements."""
    a = _article(aid)
    ls = [{k: v for k, v in l.items() if k != "_id"} | {"statut_peremption": statut_peremption(l.get("peremption", ""))}
          for l in db.base().lots.find({"article_id": aid}).sort("peremption", 1)]
    mv = list(db.base().mouvements.find({"article_id": aid}, {"_id": 0}).sort("quand", -1).limit(50))
    return {"article": _public(a), "lots": ls, "mouvements": mv}


@routeur.get("/stock/mouvements")
def mouvements(article_id: str = "", du: str = "", au: str = "", u: dict = Depends(exiger_roles(roles.LECTURE_STOCK))):
    """Mouvements filtrés (article, période) : 500 au plus, du plus récent au plus ancien."""
    f: dict = {}
    if article_id:
        f["article_id"] = article_id
    if du or au:
        f["date"] = {}
        if du:
            f["date"]["$gte"] = validation.date_iso({"d": du}, "d", "Du")
        if au:
            f["date"]["$lte"] = validation.date_iso({"d": au}, "d", "Au")
    return list(db.base().mouvements.find(f, {"_id": 0}).sort("quand", -1).limit(500))


@routeur.get("/stock/alertes")
def alertes(u: dict = Depends(exiger_roles(roles.LECTURE_STOCK))):
    """Ruptures, seuils bas, lots périmés encore en stock, lots bientôt périmés (articles et lots lus en bloc)."""
    articles = {a["id"]: a for a in db.base().articles.find({"actif": True}, {"_id": 0})}
    ruptures, bas = [], []
    for a in articles.values():
        s = statut_stock(a.get("stock", 0), a.get("seuil_alerte", 0))
        item = {"id": a["id"], "code": a["code"], "nom": a["nom"], "stock": a.get("stock", 0), "seuil": a.get("seuil_alerte", 0), "unite": a["unite"]}
        if s == "rupture" and (a.get("seuil_alerte", 0) > 0 or a.get("par_seance", 0) > 0):
            ruptures.append(item)
        elif s == "bas":
            bas.append(item)
    perimes, bientot = [], []
    for l in db.base().lots.find({"quantite_restante": {"$gt": 0}, "peremption": {"$ne": ""}}, {"_id": 0}):
        a = articles.get(l["article_id"])
        if not a:
            continue
        st = statut_peremption(l["peremption"])
        item = {"article": a["nom"], "article_id": a["id"], "lot": l["numero"], "peremption": l["peremption"], "quantite": l["quantite_restante"], "unite": a["unite"]}
        (perimes if st == "perime" else bientot if st == "bientot" else []).append(item)
    return {"ruptures": ruptures, "bas": bas, "perimes": sorted(perimes, key=lambda x: x["peremption"]), "bientot_perimes": sorted(bientot, key=lambda x: x["peremption"])}


@routeur.get("/stock/tracabilite")
def tracabilite(lot: str, u: dict = Depends(exiger_roles(roles.VOIT_MEDICAL))):
    """
    RAPPEL DE LOT : toutes les séances où ce numéro de lot a été utilisé (date, patient, poste), pour prévenir les patients concernés.
    Données médicales : soignants et administration seulement. Consultation journalisée.
    """
    numero = lot.strip()
    if not numero:
        validation.erreur("Numéro de lot obligatoire")
    ms = list(db.base().mouvements.find({"lots.numero": numero, "seance_id": {"$exists": True}}, {"_id": 0}))
    sids = list({m["seance_id"] for m in ms})
    seances = {s["id"]: s for s in db.base().seances.find({"id": {"$in": sids}})} if sids else {}
    pids = list({m["patient_id"] for m in ms})
    patients = {p["id"]: p for p in db.base().patients.find({"id": {"$in": pids}})} if pids else {}
    postes = {p["id"]: p for p in db.base().postes.find({})}
    res = []
    for m in ms:
        s, p = seances.get(m["seance_id"], {}), patients.get(m["patient_id"], {})
        res.append({"seance_id": m["seance_id"], "date": s.get("date", m["date"]), "creneau": s.get("creneau", ""), "article": m["article"],
                    "patient_id": m["patient_id"], "patient": f"{p.get('nom', '?')} {p.get('prenom', '')}".strip(), "code": p.get("code", ""),
                    "telephone": p.get("telephone", ""), "poste": postes.get(s.get("poste_id"), {}).get("nom", "")})
    journaliser("tracabilite_lot", u, f"lot {numero} : {len(res)} séance(s)")
    return sorted(res, key=lambda x: x["date"])
