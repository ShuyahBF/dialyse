"""
Centre de messagerie WhatsApp du centre (par la « Transmission WA universelle » Liluvine de SAWALI, comme ALBARKA) :
contacts, conversations, modèles de messages, envoi de DOCUMENTS (facture du patient, papier à en-tête, fichier), rappels de séances,
demandes de réservation reçues par WhatsApp, et l'adresse de retour signée de SAWALI (`POST /api/webhooks/liluvine-retour`, règle 7).

Principes :
- Chaque centre a SES contacts, messages, modèles et demandes (collections filtrées par centre, voir `db.COLLECTIONS_CENTRE`).
- L'envoi part en ARRIÈRE-PLAN (règle 7) ; l'écran voit « en cours » puis « envoyé » / « remis » / « lu » / « échec ».
- Un numéro qui a répondu STOP (désinscrit) ne reçoit plus rien (refus 409).
- Aucune donnée MÉDICALE ne part par WhatsApp : seuls le nom, la date et le créneau des séances, et les documents de la caisse (facture, papier à en-tête).
- Une facture ne peut être envoyée qu'au contact lié AU PATIENT de cette facture.
"""
from __future__ import annotations

import hmac
import json
import re
import threading
import time
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from . import acces, db, facturation, roles, validation, whatsapp
from .auth import exiger_roles, journaliser

routeur = APIRouter()

MESSAGERIE = {roles.SECRETARIAT, roles.ADMIN, roles.SUPER_ADMIN}          # qui tient la messagerie du centre
CATEGORIES = ["patient", "proche", "medecin", "fournisseur", "autre"]
LIBELLE_CATEGORIE = {"patient": "Patient", "proche": "Proche d'un patient", "medecin": "Médecin", "fournisseur": "Fournisseur", "autre": "Autre"}
STATUTS_DEMANDE = ["nouvelle", "traitee", "ignoree"]
FICHIER_MAX_OCTETS = 5 * 1024 * 1024
MIMES_FICHIER = {"application/pdf": "document", "image/jpeg": "image", "image/png": "image"}
MOTS_RESERVATION = re.compile(r"\b(rdv|rendez[- ]?vous|r[ée]serv\w*|s[ée]ance|consultation|inscri\w*)\b", re.I)
REPONSES_OUI = {"1", "oui", "ok", "confirme", "confirmé", "confirmee", "confirmée", "yes"}
REPONSES_NON = {"2", "non", "empeche", "empêché", "empechee", "empêchée", "annule", "annulé"}

# Modèles proposés au premier affichage (variables : {prenom} {nom} {centre} {date} {creneau} {poste} {numero_facture})
MODELES_DEFAUT = [
    ("Rappel de séance", "Bonjour {prenom}, rappel : votre séance de dialyse est prévue le {date}, créneau {creneau}, au centre {centre}. Répondez 1 pour CONFIRMER, 2 si vous êtes EMPÊCHÉ(E)."),
    ("Confirmation de réservation", "Bonjour {prenom}, votre demande a bien été reçue par le centre {centre}. Nous vous recontactons très vite pour confirmer la date."),
    ("Dossier incomplet", "Bonjour {prenom}, il manque des pièces à votre dossier d'admission au centre {centre}. Merci de les apporter lors de votre prochain passage."),
    ("Facture disponible", "Bonjour {prenom}, votre facture du centre {centre} est jointe à ce message. Merci."),
    # --- Messages AUTOMATIQUES (notifications du patient ; modifiables comme les autres) ---
    ("Réservation confirmée", "Bonjour {prenom}, votre séance de dialyse est CONFIRMÉE le {date}, créneau {creneau} ({heure}), au centre {centre}."),
    ("Réservation refusée", "Bonjour {prenom}, le centre {centre} ne peut pas donner suite à votre demande du {date}. Nous vous recontactons pour une autre date."),
    ("Réservation annulée", "Bonjour {prenom}, votre réservation du {date} au centre {centre} a été ANNULÉE. Contactez-nous pour fixer une nouvelle date."),
    ("Séance annulée", "Bonjour {prenom}, votre séance du {date} ({creneau}) au centre {centre} est ANNULÉE. Nous vous recontactons pour la reprogrammer."),
    ("Séance terminée", "Bonjour {prenom}, votre séance du {date} au centre {centre} est terminée. Merci de votre confiance. Prenez soin de vous."),
    ("Rappel avant la séance", "Bonjour {prenom}, rappel : votre séance de dialyse commence à {heure} ({creneau}) au centre {centre}. Répondez 1 pour CONFIRMER, 2 si vous êtes EMPÊCHÉ(E)."),
    ("Contrôle à renouveler", "Bonjour {prenom}, un contrôle de suivi est à renouveler : merci de passer au centre {centre} lors de votre prochaine séance."),
]
MODELES_VERSION = 2                                  # numéro de la liste des modèles par défaut (ajoute les nouveaux modèles aux centres existants, une seule fois)

# Notifications AUTOMATIQUES du patient (option activable par centre, comme sur SAWALI) : clé → (libellé affiché, nom du modèle, activé par défaut)
EVENEMENTS = {"reservation_confirmee": ("Rendez-vous pris (réservation confirmée)", "Réservation confirmée", True),
              "reservation_refusee": ("Réservation refusée", "Réservation refusée", True),
              "reservation_annulee": ("Réservation annulée", "Réservation annulée", True),
              "seance_annulee": ("Séance annulée", "Séance annulée", True),
              "seance_terminee": ("Séance terminée", "Séance terminée", True),
              "rappel": ("Rappel avant la séance", "Rappel avant la séance", True),
              "renouvellement": ("Contrôle à renouveler (bilan en retard)", "Contrôle à renouveler", False)}
HEURES_AVANT_MIN, HEURES_AVANT_MAX = 1, 72


def _maintenant() -> str:
    return db.maintenant()


def _public(c: dict) -> dict:
    return {k: v for k, v in c.items() if k not in ("_id", "centre_id")}


# ---------- contacts ----------

def _contact(id_: str) -> dict:
    c = db.base().contacts.find_one({"id": id_})
    if not c:
        raise HTTPException(404, "Contact introuvable")
    return c


def _contacts_de_numero(numero: str) -> list[dict]:
    """Contacts de TOUS les centres portant ce numéro (réponses reçues : on ne sait pas encore de quel centre vient le message)."""
    return list(db.brut().contacts.find({"numero": numero}, {"_id": 0}))


@routeur.get("/messagerie/etat")
def etat(u: dict = Depends(exiger_roles(MESSAGERIE))):
    """État de la messagerie : WhatsApp configuré ?, messages non lus, demandes nouvelles."""
    b = db.base()
    return {"configure": whatsapp.configure(), "non_lus": b.wa_messages.count_documents({"sens": "entrant", "lu": False}),
            "demandes_nouvelles": b.wa_demandes.count_documents({"statut": "nouvelle"})}


@routeur.get("/messagerie/contacts")
def lister_contacts(q: str = "", categorie: str = "", u: dict = Depends(exiger_roles(MESSAGERIE))):
    """Contacts du centre (les plus récemment touchés d'abord), recherche sur le nom et le numéro."""
    f: dict = {}
    if categorie:
        f["categorie"] = categorie
    if q.strip():
        n = validation.normaliser(q)
        f["$or"] = [{"nom_norm": {"$regex": re.escape(n)}}, {"numero": {"$regex": re.sub(r"\D", "", q) or "^$"}}]
    lignes = [_public(c) for c in db.base().contacts.find(f, {"_id": 0}).sort([("dernier_le", -1), ("nom_norm", 1)]).limit(500)]
    return lignes


def _valider_contact(corps: dict, creation: bool) -> dict:
    d: dict = {}
    if creation or "nom" in corps:
        d["nom"] = validation.texte(corps, "nom", "Nom", True, 100)
        d["nom_norm"] = validation.normaliser(d["nom"])
    if creation or "numero" in corps:
        numero = whatsapp.normaliser_numero(str(corps.get("numero") or ""))
        if not numero:
            validation.erreur("Numéro WhatsApp invalide (indicatif et 8 chiffres au moins)")
        d["numero"] = numero
    if creation or "categorie" in corps:
        d["categorie"] = validation.choix(corps, "categorie", "Catégorie", CATEGORIES, defaut="autre")
    if "patient_id" in corps:
        pid = str(corps.get("patient_id") or "")
        if pid and not db.base().patients.find_one({"id": pid}):
            validation.erreur("Patient inconnu dans ce centre")
        d["patient_id"] = pid
    return d


@routeur.post("/messagerie/contacts")
def creer_contact(corps: dict, u: dict = Depends(exiger_roles(MESSAGERIE))):
    d = _valider_contact(corps, True)
    if db.base().contacts.find_one({"numero": d["numero"]}):
        raise HTTPException(409, "Ce numéro existe déjà dans les contacts du centre")
    doc = {"id": str(uuid.uuid4()), **d, "patient_id": d.get("patient_id", ""), "desinscrit": False, "dernier_le": "", "dernier_extrait": "", "cree_le": _maintenant()}
    db.base().contacts.insert_one(doc)
    journaliser("contact_wa_cree", u, doc["id"])
    return _public(doc)


@routeur.put("/messagerie/contacts/{id_}")
def modifier_contact(id_: str, corps: dict, u: dict = Depends(exiger_roles(MESSAGERIE))):
    c = _contact(id_)
    d = _valider_contact(corps, False)
    if "numero" in d and d["numero"] != c["numero"] and db.base().contacts.find_one({"numero": d["numero"], "id": {"$ne": id_}}):
        raise HTTPException(409, "Ce numéro existe déjà dans les contacts du centre")
    if d:
        db.base().contacts.update_one({"id": id_}, {"$set": d})
    return _public(_contact(id_))


@routeur.delete("/messagerie/contacts/{id_}")
def supprimer_contact(id_: str, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Supprime un contact et sa conversation (administration seulement)."""
    _contact(id_)
    db.base().wa_messages.delete_many({"contact_id": id_})
    db.base().contacts.delete_one({"id": id_})
    journaliser("contact_wa_supprime", u, id_)
    return {"ok": True}


@routeur.post("/messagerie/contacts/importer-patients")
def importer_patients(u: dict = Depends(exiger_roles(MESSAGERIE))):
    """Crée un contact « Patient » pour chaque patient actif qui a un numéro valide et n'est pas déjà dans les contacts (lecture en bloc : règle 7)."""
    existants = {c["numero"] for c in db.base().contacts.find({}, {"numero": 1})}
    cree = invalide = 0
    for p in db.base().patients.find({"statut": {"$in": ["actif", "hospitalise"]}}, {"_id": 0, "id": 1, "nom": 1, "prenom": 1, "telephone": 1}):
        numero = whatsapp.normaliser_numero(p.get("telephone") or "")
        if not numero:
            invalide += 1
            continue
        if numero in existants:
            continue
        nom = f"{p['nom']} {p['prenom']}"
        db.base().contacts.insert_one({"id": str(uuid.uuid4()), "nom": nom, "nom_norm": validation.normaliser(nom), "numero": numero, "categorie": "patient", "patient_id": p["id"],
                                       "desinscrit": False, "dernier_le": "", "dernier_extrait": "", "cree_le": _maintenant()})
        existants.add(numero)
        cree += 1
    journaliser("contacts_wa_importes", u, f"{cree} créés, {invalide} sans numéro valide")
    return {"crees": cree, "sans_numero_valide": invalide}


# ---------- modèles de messages ----------

def _modeles() -> list[dict]:
    """Modèles du centre ; les modèles par défaut manquants sont ajoutés UNE fois par version de liste (un modèle supprimé ensuite ne revient pas)."""
    b = db.base()
    vu = (b.parametres.find_one({"id": "wa_modeles_version"}) or {}).get("n", 0)
    if vu < MODELES_VERSION:
        existants = {x["nom"] for x in b.wa_modeles.find({}, {"nom": 1})}
        for nom, texte in MODELES_DEFAUT:
            if nom not in existants:
                b.wa_modeles.insert_one({"id": str(uuid.uuid4()), "nom": nom, "texte": texte, "cree_le": _maintenant()})
        b.parametres.update_one({"id": "wa_modeles_version"}, {"$set": {"n": MODELES_VERSION}}, upsert=True)
    return [_public(m) for m in b.wa_modeles.find({}, {"_id": 0}).sort("nom", 1)]


@routeur.get("/messagerie/modeles")
def lister_modeles(u: dict = Depends(exiger_roles(MESSAGERIE))):
    return _modeles()


@routeur.post("/messagerie/modeles")
def creer_modele(corps: dict, u: dict = Depends(exiger_roles(MESSAGERIE))):
    doc = {"id": str(uuid.uuid4()), "nom": validation.texte(corps, "nom", "Nom du modèle", True, 80), "texte": validation.texte(corps, "texte", "Texte", True, 1000), "cree_le": _maintenant()}
    db.base().wa_modeles.insert_one(doc)
    return _public(doc)


@routeur.put("/messagerie/modeles/{id_}")
def modifier_modele(id_: str, corps: dict, u: dict = Depends(exiger_roles(MESSAGERIE))):
    if not db.base().wa_modeles.find_one({"id": id_}):
        raise HTTPException(404, "Modèle introuvable")
    db.base().wa_modeles.update_one({"id": id_}, {"$set": {"nom": validation.texte(corps, "nom", "Nom du modèle", True, 80), "texte": validation.texte(corps, "texte", "Texte", True, 1000)}})
    return _public(db.base().wa_modeles.find_one({"id": id_}))


@routeur.delete("/messagerie/modeles/{id_}")
def supprimer_modele(id_: str, u: dict = Depends(exiger_roles(MESSAGERIE))):
    db.base().wa_modeles.delete_one({"id": id_})
    return {"ok": True}


def appliquer_variables(texte: str, contact: dict, extra: dict | None = None) -> str:
    """Remplace {prenom} {nom} {centre} {date} {creneau}… ; une variable inconnue est laissée telle quelle (jamais d'exception)."""
    nom = contact.get("nom", "")
    centre = (db.brut().centres.find_one({"id": db.centre_courant.get()}) or {}).get("nom", "")
    valeurs = {"prenom": nom.split(" ")[-1] if " " in nom else nom, "nom": nom, "centre": centre, **(extra or {})}
    return re.sub(r"\{(\w+)\}", lambda m: str(valeurs.get(m.group(1), m.group(0))), texte)


# ---------- conversations et envoi ----------

def _noter_message(contact_id: str, **champs) -> dict:
    """Range un message (sens, texte, statut…) et met à jour le résumé du contact (dernier message, non lus)."""
    doc = {"id": str(uuid.uuid4()), "contact_id": contact_id, "cree_le": _maintenant(), "lu": champs.get("sens") != "entrant", **champs}
    db.base().wa_messages.insert_one(doc)
    db.base().contacts.update_one({"id": contact_id}, {"$set": {"dernier_le": doc["cree_le"], "dernier_extrait": (champs.get("texte") or ("📎 " + champs.get("document", "")))[:80]}})
    return doc


def _maj_message(centre_id: str, msg_id: str, **champs) -> None:
    """Mise à jour d'un message depuis le fil d'envoi (sans requête en cours : le centre est donné explicitement)."""
    db.brut().wa_messages.update_one({"id": msg_id, "centre_id": centre_id}, {"$set": champs})


def _expedier(centre_id: str, msg_id: str, numero: str, texte: str, media: dict | None) -> None:
    """Fil d'ARRIÈRE-PLAN : appelle Liluvine puis note le résultat sur le message. N'attend jamais la requête de l'écran."""
    ok, erreur = whatsapp.envoyer(numero, texte, media, identifiant=msg_id)
    _maj_message(centre_id, msg_id, statut="envoye" if ok else "echec", erreur="" if ok else erreur, envoye_le=_maintenant() if ok else "")
    if erreur and "désinscrit" in erreur:
        db.brut().contacts.update_many({"numero": numero, "centre_id": centre_id}, {"$set": {"desinscrit": True}})


def _document_pour(contact: dict, doc: dict) -> tuple[dict, str]:
    """Média à joindre : facture DU PATIENT du contact, papier à en-tête A4 / A5, ou fichier choisi. Rend (media, libellé)."""
    genre = str(doc.get("type") or "")
    if genre == "facture":
        f = facturation._facture(str(doc.get("id") or ""))
        if not contact.get("patient_id") or f["patient_id"] != contact["patient_id"]:
            raise HTTPException(400, "Cette facture n'est pas celle du patient lié à ce contact")
        from .centres import entete_courant
        return {"type": "document", "contenu": facturation.pdf_facture(f, entete_courant()), "nom_fichier": f"{f['numero']}.pdf".replace("/", "-"), "mime": "application/pdf"}, f"Facture {f['numero']}"
    if genre == "papier":
        from .centres import entete_courant, pdf_papier_entete
        fmt = str(doc.get("format") or "A4").upper()
        if fmt not in ("A4", "A5"):
            validation.erreur("Format : A4 ou A5")
        return {"type": "document", "contenu": pdf_papier_entete(entete_courant(), fmt), "nom_fichier": f"papier-entete-{fmt}.pdf", "mime": "application/pdf"}, f"Papier à en-tête {fmt}"
    if genre == "fichier":
        import base64
        mime = str(doc.get("mime") or "")
        if mime not in MIMES_FICHIER:
            validation.erreur("Fichier : PDF, JPEG ou PNG seulement")
        try:
            octets = base64.b64decode(str(doc.get("contenu_base64") or ""), validate=False)
        except Exception:
            validation.erreur("Fichier illisible")
        if not octets or len(octets) > FICHIER_MAX_OCTETS:
            validation.erreur("Fichier vide ou de plus de 5 Mo")
        nom = re.sub(r"[^\w.\- ]", "_", str(doc.get("nom") or "document"))[:80]
        return {"type": MIMES_FICHIER[mime], "contenu": octets, "nom_fichier": nom, "mime": mime}, nom
    validation.erreur("Document : facture, papier ou fichier")


@routeur.post("/messagerie/envoyer")
def envoyer(corps: dict, u: dict = Depends(exiger_roles(MESSAGERIE))):
    """Envoie un message (texte et/ou document) à un contact. Départ en arrière-plan : la réponse est immédiate (statut « en cours »)."""
    if not whatsapp.configure():
        raise HTTPException(503, "WhatsApp n'est pas configuré sur le serveur (LILUVINE_WA_URL et LILUVINE_WA_HMAC)")
    c = _contact(str(corps.get("contact_id") or ""))
    if c.get("desinscrit"):
        raise HTTPException(409, "Ce contact s'est désinscrit des messages WhatsApp (réponse STOP)")
    texte = appliquer_variables(validation.texte(corps, "texte", "Message", False, 1000), c)
    media, libelle = (None, "")
    if corps.get("document"):
        media, libelle = _document_pour(c, corps["document"])
    if not texte.strip() and not media:
        validation.erreur("Écrivez un message ou joignez un document")
    m = _noter_message(c["id"], sens="sortant", texte=texte, document=libelle, statut="en_cours", erreur="", par=u["login"], numero=c["numero"])
    journaliser("message_wa_envoye", u, f"{c['id']} ({'document' if media else 'texte'}, {len(texte)} car.)")      # jamais le texte
    acces.lancer(_expedier, u["centre_id"], m["id"], c["numero"], texte, media)
    return _public(db.base().wa_messages.find_one({"id": m["id"]}))


@routeur.get("/messagerie/contacts/{id_}/messages")
def conversation(id_: str, limite: int = 100, u: dict = Depends(exiger_roles(MESSAGERIE))):
    """Conversation avec un contact (les `limite` derniers messages, du plus ancien au plus récent) ; les messages reçus passent « lus »."""
    c = _contact(id_)
    db.base().wa_messages.update_many({"contact_id": id_, "sens": "entrant", "lu": False}, {"$set": {"lu": True}})
    lignes = list(db.base().wa_messages.find({"contact_id": id_}, {"_id": 0, "centre_id": 0}).sort("cree_le", -1).limit(max(1, min(limite, 300))))
    lignes.reverse()
    return {"contact": _public(c), "messages": lignes}


@routeur.get("/messagerie/non-lus")
def non_lus(u: dict = Depends(exiger_roles(MESSAGERIE))):
    """Nombre de messages non lus par contact (pastilles de la liste des conversations)."""
    res: dict = {}
    for m in db.base().wa_messages.find({"sens": "entrant", "lu": False}, {"contact_id": 1}):
        res[m["contact_id"]] = res.get(m["contact_id"], 0) + 1
    return res


# ---------- notifications automatiques du patient (option par centre) ----------

def parametres_auto() -> dict:
    """Réglages du centre : `actif` (interrupteur général, éteint par défaut), `rappel_heures_avant` (1 à 72 h), et chaque événement activable."""
    s = db.base().parametres.find_one({"id": "wa_notifications"}) or {}
    ev = {k: bool((s.get("evenements") or {}).get(k, defaut)) for k, (_l, _m, defaut) in EVENEMENTS.items()}
    return {"actif": bool(s.get("actif", False)), "rappel_heures_avant": int(s.get("rappel_heures_avant", 1)), "evenements": ev}


@routeur.get("/messagerie/parametres")
def lire_parametres(u: dict = Depends(exiger_roles(MESSAGERIE))):
    """Réglages des notifications automatiques + liste des événements (libellés pour l'écran)."""
    return {**parametres_auto(), "liste": [{"cle": k, "libelle": v[0]} for k, v in EVENEMENTS.items()], "heures_min": HEURES_AVANT_MIN, "heures_max": HEURES_AVANT_MAX}


@routeur.put("/messagerie/parametres")
def ecrire_parametres(corps: dict, u: dict = Depends(exiger_roles(roles.ADMINISTRATION))):
    """Active ou coupe les notifications automatiques du centre, règle l'heure du rappel (X heures avant la séance) et choisit les événements."""
    actuel = parametres_auto()
    heures = validation.nombre(corps, "rappel_heures_avant", "Rappel (heures avant la séance)", HEURES_AVANT_MIN, HEURES_AVANT_MAX) if "rappel_heures_avant" in corps else actuel["rappel_heures_avant"]
    ev = {k: bool((corps.get("evenements") or {}).get(k, actuel["evenements"][k])) for k in EVENEMENTS}
    doc = {"actif": bool(corps.get("actif", actuel["actif"])), "rappel_heures_avant": int(heures or 1), "evenements": ev}
    db.base().parametres.update_one({"id": "wa_notifications"}, {"$set": doc}, upsert=True)
    journaliser("wa_notifications_reglees", u, f"actif={doc['actif']}, rappel {doc['rappel_heures_avant']} h avant")
    return lire_parametres(u)


def notifier(evenement: str, patient_id: str, extra: dict | None = None) -> bool:
    """
    Prévient un patient par WhatsApp d'un événement (rendez-vous pris, annulé, séance terminée, rappel, contrôle à renouveler). AU MIEUX : jamais d'erreur, jamais bloquant,
    rien si l'option du centre est éteinte, si l'événement est désactivé, si WhatsApp n'est pas configuré, si le patient n'a pas de numéro ou s'est désinscrit.
    Aucune donnée médicale : seulement date, créneau, heure et nom du centre. Départ en arrière-plan (règle 7). Rend vrai si un message est parti.
    """
    try:
        p = parametres_auto()
        if not (p["actif"] and p["evenements"].get(evenement) and whatsapp.configure()):
            return False
        pat = db.base().patients.find_one({"id": patient_id}, {"_id": 0, "id": 1, "nom": 1, "prenom": 1, "telephone": 1})
        numero = whatsapp.normaliser_numero((pat or {}).get("telephone") or "")
        modele = next((x for x in _modeles() if x["nom"] == EVENEMENTS[evenement][1]), None)
        if not numero or not modele:
            return False
        c = db.base().contacts.find_one({"numero": numero})
        if c and c.get("desinscrit"):
            return False
        if not c:
            nom = f"{pat['nom']} {pat['prenom']}"
            c = {"id": str(uuid.uuid4()), "nom": nom, "nom_norm": validation.normaliser(nom), "numero": numero, "categorie": "patient", "patient_id": pat["id"], "desinscrit": False,
                 "dernier_le": "", "dernier_extrait": "", "cree_le": _maintenant()}
            db.base().contacts.insert_one(c)
        ex = dict(extra or {})
        if ex.get("date") and len(ex["date"]) == 10 and ex["date"][4] == "-":
            ex["date"] = f"{ex['date'][8:]}/{ex['date'][5:7]}/{ex['date'][:4]}"
        texte = appliquer_variables(modele["texte"], {**c, "nom": pat["prenom"]}, ex)
        m = _noter_message(c["id"], sens="sortant", texte=texte, document="", statut="en_cours", erreur="", par="automatique", numero=numero, type=evenement)
        acces.lancer(_expedier, db.centre_courant.get(), m["id"], numero, texte, None)
        return True
    except Exception:                                    # noqa: BLE001 — une notification ratée ne doit jamais faire échouer l'action du personnel
        return False


_DERNIER_RENOUVELLEMENT: dict = {}          # centre → heure de la dernière vérification (une fois par heure suffit)
JOURS_BILAN_RETARD = 35                     # même seuil que le suivi anonymisé : dernier bilan de plus de 35 jours
JOURS_ENTRE_DEUX_RAPPELS = 14               # un patient n'est relancé qu'une fois tous les 14 jours


def _renouvellements(maintenant) -> int:
    """Message « contrôle à renouveler » aux patients actifs dont le dernier bilan a plus de 35 jours (ou n'existe pas) ; une fois par heure et par centre, lectures en bloc."""
    centre = db.centre_courant.get()
    if maintenant.timestamp() - _DERNIER_RENOUVELLEMENT.get(centre, 0) < 3600:
        return 0
    _DERNIER_RENOUVELLEMENT[centre] = maintenant.timestamp()
    limite = (maintenant.date() - timedelta(days=JOURS_BILAN_RETARD)).isoformat()
    relance = (maintenant - timedelta(days=JOURS_ENTRE_DEUX_RAPPELS)).isoformat(timespec="seconds")
    derniers: dict = {}
    for b in db.base().bilans.find({}, {"_id": 0, "patient_id": 1, "date_prelevement": 1}):
        if b["date_prelevement"] > derniers.get(b["patient_id"], ""):
            derniers[b["patient_id"]] = b["date_prelevement"]
    n = 0
    for pat in db.base().patients.find({"statut": "actif"}, {"_id": 0, "id": 1, "renouvellement_wa_le": 1}):
        if derniers.get(pat["id"], "") >= limite or (pat.get("renouvellement_wa_le") or "") > relance:
            continue
        db.base().patients.update_one({"id": pat["id"]}, {"$set": {"renouvellement_wa_le": maintenant.isoformat(timespec="seconds")}})
        n += 1 if notifier("renouvellement", pat["id"]) else 0
    return n


def rappels_automatiques(maintenant=None) -> int:
    """
    Rappel « X heures avant » : pour chaque centre dont l'option est active, prévient les patients dont la séance commence dans moins de X heures (X réglé par le centre).
    Un seul rappel par séance (`rappel_auto_le`). Appelée toutes les 5 minutes par la tâche de fond ; `maintenant` (UTC) permet de la tester. Rend le nombre de rappels.
    """
    from datetime import datetime, timezone
    from . import seances as sea
    maintenant = maintenant or datetime.now(timezone.utc)
    envoyes, ancien = 0, db.centre_courant.get()
    try:
        for centre in db.brut().centres.find({"actif": {"$ne": False}}, {"_id": 0, "id": 1}):
            db.fixer_centre(centre["id"])
            p = parametres_auto()
            if p["actif"] and p["evenements"].get("renouvellement"):
                envoyes += _renouvellements(maintenant)
            if not (p["actif"] and p["evenements"].get("rappel")):
                continue
            jours = {maintenant.date().isoformat(), (maintenant.date() + timedelta(days=2)).isoformat(), (maintenant.date() + timedelta(days=1)).isoformat()}
            for s in db.base().seances.find({"date": {"$in": sorted(jours)}, "statut": "planifiee", "rappel_auto_le": {"$exists": False}}):
                heure = s.get("heure_prevue") or sea.CRENEAU_HEURE.get(s["creneau"], "07:00")          # heure précise de la séance, sinon celle du créneau
                h, mi = heure.split(":")[:2]
                debut = datetime.fromisoformat(f"{s['date']}T{h}:{mi}:00+00:00")
                if debut - timedelta(hours=p["rappel_heures_avant"]) <= maintenant < debut:
                    db.base().seances.update_one({"id": s["id"]}, {"$set": {"rappel_auto_le": maintenant.isoformat(timespec="seconds")}})
                    if notifier("rappel", s["patient_id"], {"date": s["date"], "creneau": s["creneau"], "heure": heure}):
                        envoyes += 1
    finally:
        db.fixer_centre(ancien)
    return envoyes


# ---------- rappels de séances ----------

def _rappels_prevus(jour: str) -> tuple[list[dict], dict]:
    """Séances planifiées du jour avec un patient joignable. Rend (envois, comptes). Lectures en bloc."""
    seances = list(db.base().seances.find({"date": jour, "statut": "planifiee"}, {"_id": 0}))
    pids = list({s["patient_id"] for s in seances})
    patients = {p["id"]: p for p in db.base().patients.find({"id": {"$in": pids}}, {"_id": 0, "id": 1, "nom": 1, "prenom": 1, "telephone": 1})} if pids else {}
    postes = {p["id"]: p["nom"] for p in db.base().postes.find({}, {"id": 1, "nom": 1})}
    par_numero = {c["numero"]: c for c in db.base().contacts.find({}, {"_id": 0})}
    envois, sans_numero, desinscrits = [], 0, 0
    for s in seances:
        p = patients.get(s["patient_id"])
        numero = whatsapp.normaliser_numero((p or {}).get("telephone") or "")
        if not numero:
            sans_numero += 1
            continue
        c = par_numero.get(numero)
        if c and c.get("desinscrit"):
            desinscrits += 1
            continue
        envois.append({"seance": s, "patient": p, "numero": numero, "contact": c, "poste": postes.get(s.get("poste_id"), "")})
    return envois, {"seances": len(seances), "a_envoyer": len(envois), "sans_numero": sans_numero, "desinscrits": desinscrits}


@routeur.get("/messagerie/rappels/apercu")
def apercu_rappels(date_: str = Query("", alias="date"), u: dict = Depends(exiger_roles(MESSAGERIE))):
    jour = validation.date_iso({"d": date_ or (date.today() + timedelta(days=1)).isoformat()}, "d", "Date", True)
    _, comptes = _rappels_prevus(jour)
    return {"date": jour, **comptes}


@routeur.post("/messagerie/rappels")
def envoyer_rappels(corps: dict, u: dict = Depends(exiger_roles(MESSAGERIE))):
    """Rappel WhatsApp à chaque patient ayant une séance planifiée ce jour-là (modèle choisi, sinon « Rappel de séance »). Départ en arrière-plan."""
    if not whatsapp.configure():
        raise HTTPException(503, "WhatsApp n'est pas configuré sur le serveur (LILUVINE_WA_URL et LILUVINE_WA_HMAC)")
    jour = validation.date_iso({"d": corps.get("date") or (date.today() + timedelta(days=1)).isoformat()}, "d", "Date", True)
    modeles = _modeles()
    modele = next((m for m in modeles if m["id"] == corps.get("modele_id")), None) or next((m for m in modeles if m["nom"] == "Rappel de séance"), modeles[0])
    envois, comptes = _rappels_prevus(jour)
    for e in envois:
        c = e["contact"]
        if not c:                                                      # contact créé à la volée pour ce patient
            nom = f"{e['patient']['nom']} {e['patient']['prenom']}"
            c = {"id": str(uuid.uuid4()), "nom": nom, "nom_norm": validation.normaliser(nom), "numero": e["numero"], "categorie": "patient", "patient_id": e["patient"]["id"],
                 "desinscrit": False, "dernier_le": "", "dernier_extrait": "", "cree_le": _maintenant()}
            db.base().contacts.insert_one(c)
        texte = appliquer_variables(modele["texte"], {**c, "nom": e["patient"]["prenom"]},
                                    {"date": f"{jour[8:]}/{jour[5:7]}/{jour[:4]}", "creneau": e["seance"].get("creneau", ""), "poste": e["poste"]})
        m = _noter_message(c["id"], sens="sortant", texte=texte, document="", statut="en_cours", erreur="", par=u["login"], numero=e["numero"], type="rappel", seance_id=e["seance"]["id"])
        db.base().seances.update_one({"id": e["seance"]["id"]}, {"$set": {"rappel_wa_le": _maintenant()}})
        acces.lancer(_expedier, u["centre_id"], m["id"], e["numero"], texte, None)
    journaliser("rappels_wa_envoyes", u, f"{jour} : {comptes['a_envoyer']} message(s)")
    return {"date": jour, **comptes}


# ---------- demandes de réservation ----------

@routeur.get("/messagerie/demandes")
def lister_demandes(statut: str = "", u: dict = Depends(exiger_roles(MESSAGERIE))):
    """Demandes reçues par WhatsApp (réservations, patients empêchés), les plus récentes d'abord."""
    f = {"statut": statut} if statut else {}
    return [_public(d) for d in db.base().wa_demandes.find(f, {"_id": 0}).sort("cree_le", -1).limit(300)]


@routeur.put("/messagerie/demandes/{id_}")
def traiter_demande(id_: str, corps: dict, u: dict = Depends(exiger_roles(MESSAGERIE))):
    d = db.base().wa_demandes.find_one({"id": id_})
    if not d:
        raise HTTPException(404, "Demande introuvable")
    statut = validation.choix(corps, "statut", "État", STATUTS_DEMANDE, obligatoire=True)
    db.base().wa_demandes.update_one({"id": id_}, {"$set": {"statut": statut, "note": validation.texte(corps, "note", "Note", False, 300), "traite_par": u["login"], "traite_le": _maintenant()}})
    journaliser("demande_wa_traitee", u, f"{id_} → {statut}")
    return _public(db.base().wa_demandes.find_one({"id": id_}))


# ---------- retours signés de SAWALI ----------

def _corps_signe(brut: bytes, horodatage: str, signature: str) -> dict:
    """Vérifie la signature de SAWALI (clé LILUVINE_WA_HMAC ; en-têtes X-Timestamp et X-Signature ; 5 minutes) et rend le corps JSON."""
    from .config import env
    cle = env("LILUVINE_WA_HMAC").strip()
    if not cle:
        raise HTTPException(503, "LILUVINE_WA_HMAC non configurée")
    if not horodatage.isdigit() or abs(time.time() - int(horodatage)) > 300:
        raise HTTPException(401, "Horodatage invalide")
    if not hmac.compare_digest(whatsapp.signer(cle, horodatage, brut.decode("utf-8")), signature or ""):
        raise HTTPException(401, "Signature invalide")
    try:
        corps = json.loads(brut.decode("utf-8") or "{}")
    except ValueError:
        raise HTTPException(422, "Corps JSON invalide")
    if not isinstance(corps, dict):
        raise HTTPException(422, "Corps JSON attendu")
    return corps


def _stats_du_jour() -> dict:
    """Indicateurs du jour pour la synthèse quotidienne de SAWALI : TOUS les centres, agrégés, sans aucune donnée de patient."""
    from . import lot
    from .main import DEPLOYE_LE
    b, auj = db.brut(), date.today().isoformat()
    return {"indicateurs": [
        {"cle": "centres", "libelle": "Centres actifs", "valeur": b.centres.count_documents({"actif": {"$ne": False}})},
        {"cle": "seances", "libelle": "Séances du jour", "valeur": b.seances.count_documents({"date": auj, "statut": {"$in": ["planifiee", "en_cours", "terminee"]}})},
        {"cle": "terminees", "libelle": "Séances terminées", "valeur": b.seances.count_documents({"date": auj, "statut": "terminee"})},
        {"cle": "patients", "libelle": "Patients en dialyse", "valeur": b.patients.count_documents({"statut": "actif"})},
        {"cle": "wa_envoyes", "libelle": "WhatsApp envoyés", "valeur": b.wa_messages.count_documents({"sens": "sortant", "cree_le": {"$gte": auj}})},
        {"cle": "wa_recus", "libelle": "WhatsApp reçus", "valeur": b.wa_messages.count_documents({"sens": "entrant", "cree_le": {"$gte": auj}})}],
        "version": lot.VERSION, "deploye_le": DEPLOYE_LE}


def _accuser(centre_id: str, numero: str, texte: str) -> None:
    """Accusé de réception automatique (fil séparé) ; au plus un par contact et par heure, jamais vers un désinscrit."""
    c = db.brut().contacts.find_one({"numero": numero, "centre_id": centre_id})
    if not c or c.get("desinscrit"):
        return
    depuis = (__import__("datetime").datetime.now(__import__("datetime").timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    if db.brut().wa_messages.count_documents({"contact_id": c["id"], "type": "accuse", "cree_le": {"$gte": depuis}}):
        return
    mid = str(uuid.uuid4())
    db.brut().wa_messages.insert_one({"id": mid, "centre_id": centre_id, "contact_id": c["id"], "sens": "sortant", "texte": texte, "document": "", "statut": "en_cours", "erreur": "",
                                      "par": "automatique", "numero": numero, "type": "accuse", "lu": True, "cree_le": _maintenant()})
    acces.lancer(_expedier, centre_id, mid, numero, texte, None)


def _traiter_reponse(corps: dict) -> None:
    """Un contact a répondu : message rangé dans la conversation du bon centre ; « 1 / 2 » confirment ou excusent une séance ; un mot de réservation crée une demande."""
    numero = whatsapp.normaliser_numero(str(corps.get("de") or corps.get("from") or ""))
    texte = str(corps.get("texte") or corps.get("message") or corps.get("text") or "").strip()[:1000]
    if not numero or not texte:
        return
    candidats = _contacts_de_numero(numero)
    if not candidats:
        # Numéro inconnu : un seul centre actif = c'est le sien ; sinon la boîte « non classés » du groupe.
        actifs = list(db.brut().centres.find({"actif": {"$ne": False}}, {"_id": 0, "id": 1}))
        if len(actifs) != 1:
            db.brut().wa_non_classes.insert_one({"numero": numero, "extrait": texte[:80], "cree_le": _maintenant()})
            return
        db.fixer_centre(actifs[0]["id"])
        c = {"id": str(uuid.uuid4()), "nom": "Nouveau contact", "nom_norm": "nouveau contact", "numero": numero, "categorie": "autre", "patient_id": "", "desinscrit": False,
             "dernier_le": "", "dernier_extrait": "", "cree_le": _maintenant()}
        db.base().contacts.insert_one(c)
    else:
        c = max(candidats, key=lambda x: x.get("dernier_le") or "")             # le centre auquel on a écrit le plus récemment
        db.fixer_centre(c["centre_id"])
    _noter_message(c["id"], sens="entrant", texte=texte, document="", statut="recu", erreur="", numero=numero)
    mot = texte.lower().strip(" .!")
    if c.get("patient_id") and mot in REPONSES_OUI | REPONSES_NON:
        s = db.base().seances.find_one({"patient_id": c["patient_id"], "statut": "planifiee", "date": {"$gte": date.today().isoformat()}}, sort=[("date", 1)])
        if s:
            oui = mot in REPONSES_OUI
            db.base().seances.update_one({"id": s["id"]}, {"$set": {"confirmation_wa": "confirmee" if oui else "empeche", "confirmation_wa_le": _maintenant()}})
            if not oui:
                db.base().wa_demandes.insert_one({"id": str(uuid.uuid4()), "contact_id": c["id"], "contact_nom": c["nom"], "type": "empeche", "texte": f"Empêché(e) pour la séance du {s['date']}",
                                                  "statut": "nouvelle", "cree_le": _maintenant()})
            _accuser(c["centre_id"] if "centre_id" in c else db.centre_courant.get(), numero, "Merci, votre réponse est bien prise en compte." if oui else "Bien reçu : le centre vous recontactera pour reprogrammer votre séance.")
            return
    if MOTS_RESERVATION.search(texte):
        db.base().wa_demandes.insert_one({"id": str(uuid.uuid4()), "contact_id": c["id"], "contact_nom": c["nom"], "type": "reservation", "texte": texte[:300],
                                          "statut": "nouvelle", "cree_le": _maintenant()})
        modele = next((m for m in _modeles() if m["nom"] == "Confirmation de réservation"), None)
        if modele:
            _accuser(db.centre_courant.get(), numero, appliquer_variables(modele["texte"], c))


@routeur.post("/api/webhooks/liluvine-retour")
async def retour_sawali(request: Request):
    """
    Adresse de retour signée de SAWALI (règle 7) : statut de remise, réponse d'un contact, désinscription (STOP), statistiques du jour. À saisir dans SAWALI
    (émetteur « dialyse » → URL de retour) : https://api.looisdialyse.space/api/webhooks/liluvine-retour
    """
    from fastapi.concurrency import run_in_threadpool
    brut = await request.body()
    corps = _corps_signe(brut, request.headers.get("x-timestamp") or "", request.headers.get("x-signature") or "")
    genre = str(corps.get("type") or "")

    def travail():
        if genre == "stats_du_jour":
            return _stats_du_jour()
        if genre == "statut":
            ident = str(corps.get("id") or corps.get("message_id") or "")
            etat_ = str(corps.get("statut") or "").lower()
            if ident and etat_:
                db.brut().wa_messages.update_one({"id": ident}, {"$set": {"statut": {"delivered": "remis", "read": "lu", "sent": "envoye", "failed": "echec"}.get(etat_, etat_)}})
        elif genre == "reponse":
            _traiter_reponse(corps)
        elif genre == "desinscription":
            numero = whatsapp.normaliser_numero(str(corps.get("de") or corps.get("from") or ""))
            if numero:
                db.brut().contacts.update_many({"numero": numero}, {"$set": {"desinscrit": True, "desinscrit_le": _maintenant()}})
        else:
            db.brut().retours_sawali.insert_one({"type": genre[:40], "recu_le": _maintenant()})          # autres types : trace minimale, aucun contenu
        return {"ok": True}
    db.fixer_centre(None)
    return await run_in_threadpool(travail)
