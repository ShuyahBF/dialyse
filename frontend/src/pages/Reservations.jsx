// Réservations du centre : demandes de place (à confirmer sur un poste, refuser ou annuler), demandes reçues par WhatsApp (à convertir) et liste d'attente.
import { Ban, Check, ClipboardList, MessageCircle, Plus, RefreshCw, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Liste, Pastille, Texte } from "../composants/Champs.jsx";
import FormulaireReservation from "../composants/FormulaireReservation.jsx";
import Modal from "../composants/Modal.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateFr } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

const COULEUR = { demandee: "violet", confirmee: "vert", refusee: "rouge", annulee: "gris" };
const PRIORITES = [{ valeur: "urgente", libelle: "Urgente" }, { valeur: "normale", libelle: "Normale" }, { valeur: "basse", libelle: "Basse" }];

function Onglets({ onglets, actif, onChoix }) {
  return (
    <div className="mb-3 flex flex-wrap gap-1 border-b border-slate-200">
      {onglets.map(([k, l, n]) => (
        <button key={k} type="button" onClick={() => onChoix(k)} className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-semibold ${actif === k ? "border-citron text-encre" : "border-transparent text-slate-500 hover:text-encre"}`}>
          {l}{n > 0 && <span className="rounded-full bg-citron px-1.5 text-[11px] font-bold text-white">{n}</span>}
        </button>
      ))}
    </div>
  );
}

export default function Reservations() {
  const { avecToast, toast, rafraichirCompteurs } = useApp();
  const [onglet, setOnglet] = useState("reservations");
  const [reservations, setReservations] = useState([]);
  const [demandes, setDemandes] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [attente, setAttente] = useState([]);
  const [postes, setPostes] = useState([]);
  const [modal, setModal] = useState(null);       // { type: "confirmer" | "refuser" | "attente" | "nouvelle", ... }
  const [formulaire, setFormulaire] = useState({});
  const tri = useTri();
  const charger = useCallback(async () => {
    const auj = new Date().toISOString().slice(0, 10);
    const [r, d, c, a, p] = await Promise.all([api(`/reservations?du=${auj}`), api("/messagerie/demandes?statut=nouvelle").catch(() => []), api("/messagerie/contacts").catch(() => []), api("/attente"), api("/postes")]);
    setReservations(r); setDemandes(d); setContacts(c); setAttente(a); setPostes(p.filter((x) => x.statut === "actif"));
    rafraichirCompteurs?.();
    return { r, d, a };
  }, [rafraichirCompteurs]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);

  const agir = async (enCours, action, ok) => { await avecToast(enCours, action, ok); setModal(null); await charger(); };
  const enAttente = reservations.filter((r) => r.statut === "demandee").length;
  const lignes = trierLignes(reservations, tri.cle, tri.sens);
  const patientDe = (d) => contacts.find((c) => c.id === d.contact_id)?.patient_id || "";
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><ClipboardList size={24} className="text-citron" /> Réservations</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation des réservations", charger, (x) => `${x.r.length} réservation(s), ${x.d.length} demande(s) WhatsApp, ${x.a.length} en attente de place`)}>Actualiser</Bouton>
          <Bouton icone={Plus} variante="principal" onClick={() => setModal({ type: "nouvelle" })}>Nouvelle réservation</Bouton>
        </div>
      </div>
      <BandeauVersion className="mb-3" />
      <Onglets actif={onglet} onChoix={setOnglet} onglets={[["reservations", "Réservations", enAttente], ["whatsapp", "Demandes WhatsApp", demandes.length], ["attente", "Liste d'attente", 0]]} />

      {onglet === "reservations" && (
        <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
          <table className="tableau">
            <thead><tr><ThTri cle="date" tri={tri}>Date</ThTri><ThTri cle="creneau" tri={tri}>Créneau</ThTri><ThTri cle="patient_nom" tri={tri}>Patient</ThTri><ThTri cle="motif" tri={tri}>Motif</ThTri>
              <ThTri cle="statut" tri={tri}>État</ThTri><ThTri cle="source" tri={tri}>Origine</ThTri><th>Actions</th></tr></thead>
            <tbody>
              {lignes.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-slate-500">Aucune réservation à venir.</td></tr>}
              {lignes.map((r) => (
                <tr key={r.id}>
                  <td className="tabular-nums font-medium text-emeraude">{dateFr(r.date)}</td><td>{r.creneau}</td><td>{r.patient_nom} <span className="text-xs text-slate-500">{r.patient_code}</span></td><td>{r.motif}</td>
                  <td><Pastille couleur={COULEUR[r.statut]}>{r.statut_libelle}</Pastille></td><td>{r.source === "whatsapp" ? <Pastille couleur="vert" icone={MessageCircle}>WhatsApp</Pastille> : "Secrétariat"}</td>
                  <td className="whitespace-nowrap">
                    {r.statut === "demandee" && <><BoutonIcone icone={Check} libelle="Confirmer sur un poste" couleur="text-emerald-600" onClick={() => { setFormulaire({ poste_id: "" }); setModal({ type: "confirmer", r }); }} />
                      <BoutonIcone icone={X} libelle="Refuser" couleur="text-rose-600" onClick={() => { setFormulaire({ motif: "" }); setModal({ type: "refuser", r }); }} /></>}
                    {["demandee", "confirmee"].includes(r.statut) && <BoutonIcone icone={Ban} libelle="Annuler la réservation" couleur="text-orange-600" onClick={() => agir("Annulation", () => api(`/reservations/${r.id}/annuler`, { methode: "POST", corps: {} }), () => "Réservation annulée")} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {onglet === "whatsapp" && (
        <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
          <table className="tableau">
            <thead><tr><th>Reçue le</th><th>Contact</th><th>Type</th><th>Message</th><th>Actions</th></tr></thead>
            <tbody>
              {demandes.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-slate-500">Aucune demande reçue par WhatsApp à traiter.</td></tr>}
              {demandes.map((d) => (
                <tr key={d.id}>
                  <td className="tabular-nums">{dateFr(d.cree_le)}</td><td className="font-medium text-emeraude">{d.contact_nom}</td>
                  <td>{d.type === "empeche" ? <Pastille couleur="orange">Patient empêché</Pastille> : <Pastille couleur="violet">Réservation</Pastille>}</td><td className="max-w-xs truncate" title={d.texte}>{d.texte}</td>
                  <td className="whitespace-nowrap">
                    <BoutonIcone icone={Plus} libelle="Convertir en réservation" couleur="text-emerald-600" onClick={() => setModal({ type: "convertir", d })} />
                    <BoutonIcone icone={X} libelle="Marquer comme traitée" couleur="text-slate-500" onClick={() => agir("Mise à jour", () => api(`/messagerie/demandes/${d.id}`, { methode: "PUT", corps: { statut: "traitee" } }), () => "Demande traitée")} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {onglet === "attente" && (
        <div>
          <div className="mb-2"><Bouton icone={UserPlus} onClick={() => { setFormulaire({ priorite: "normale" }); setModal({ type: "attente" }); }}>Ajouter à la liste d'attente</Bouton></div>
          <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
            <table className="tableau">
              <thead><tr><th>Priorité</th><th>Nom</th><th>Téléphone</th><th>Motif</th><th>Depuis</th><th>Actions</th></tr></thead>
              <tbody>
                {attente.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-500">Personne n'attend de place.</td></tr>}
                {attente.map((a) => (
                  <tr key={a.id}>
                    <td><Pastille couleur={a.priorite === "urgente" ? "rouge" : a.priorite === "normale" ? "bleu" : "gris"}>{PRIORITES.find((p) => p.valeur === a.priorite)?.libelle}</Pastille></td>
                    <td className="font-medium text-emeraude">{a.nom} {a.prenom}</td><td>{a.telephone || "—"}</td><td>{a.motif || "—"}</td><td className="tabular-nums">{dateFr(a.cree_le)}</td>
                    <td className="whitespace-nowrap">
                      <BoutonIcone icone={Check} libelle="Admis : retirer de la liste" couleur="text-emerald-600" onClick={() => agir("Mise à jour", () => api(`/attente/${a.id}`, { methode: "PUT", corps: { statut: "admis" } }), () => "Marqué admis")} />
                      <BoutonIcone icone={X} libelle="Retirer de la liste" couleur="text-rose-600" onClick={() => agir("Mise à jour", () => api(`/attente/${a.id}`, { methode: "PUT", corps: { statut: "retire" } }), () => "Retiré de la liste")} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {modal?.type === "nouvelle" && <FormulaireReservation onFermer={() => setModal(null)} onFait={() => { setModal(null); charger(); }} />}
      {modal?.type === "convertir" && <FormulaireReservation patientId={patientDe(modal.d)} demandeId={modal.d.id} motif={modal.d.type === "empeche" ? "Changement de créneau" : ""} onFermer={() => setModal(null)} onFait={() => { setModal(null); charger(); }} />}
      {modal?.type === "confirmer" && (
        <Modal titre={`Confirmer — ${modal.r.patient_nom}`} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={Check} variante="vert" disabled={!formulaire.poste_id} onClick={() => agir("Confirmation", () => api(`/reservations/${modal.r.id}/confirmer`, { methode: "POST", corps: { poste_id: formulaire.poste_id } }), () => "Réservation confirmée : séance ajoutée au calendrier")}>Confirmer</Bouton></>}>
          <p className="mb-2 text-sm">Séance du <b>{dateFr(modal.r.date)}</b>, créneau <b>{modal.r.creneau}</b>.</p>
          <Liste libelle="Poste" valeur={formulaire.poste_id} onChange={(v) => setFormulaire({ poste_id: v })} options={postes.map((p) => ({ valeur: p.id, libelle: p.nom }))} />
        </Modal>
      )}
      {modal?.type === "refuser" && (
        <Modal titre={`Refuser — ${modal.r.patient_nom}`} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={X} variante="rouge" disabled={!formulaire.motif} onClick={() => agir("Refus", () => api(`/reservations/${modal.r.id}/refuser`, { methode: "POST", corps: { motif: formulaire.motif } }), () => "Réservation refusée")}>Refuser</Bouton></>}>
          <Texte libelle="Motif du refus" valeur={formulaire.motif} onChange={(v) => setFormulaire({ motif: v })} placeholder="Aucun poste libre à cette date" />
        </Modal>
      )}
      {modal?.type === "attente" && (
        <Modal titre="Liste d'attente" onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={UserPlus} variante="principal" disabled={!formulaire.nom || !formulaire.prenom} onClick={() => agir("Ajout", () => api("/attente", { methode: "POST", corps: formulaire }), () => "Ajouté à la liste d'attente")}>Ajouter</Bouton></>}>
          <Texte libelle="Nom" valeur={formulaire.nom} onChange={(v) => setFormulaire({ ...formulaire, nom: v })} placeholder="BADINI" />
          <Texte libelle="Prénom" valeur={formulaire.prenom} onChange={(v) => setFormulaire({ ...formulaire, prenom: v })} placeholder="Awa" />
          <Texte libelle="Téléphone" valeur={formulaire.telephone} onChange={(v) => setFormulaire({ ...formulaire, telephone: v })} />
          <Texte libelle="Motif" valeur={formulaire.motif} onChange={(v) => setFormulaire({ ...formulaire, motif: v })} />
          <Liste libelle="Priorité" valeur={formulaire.priorite} onChange={(v) => setFormulaire({ ...formulaire, priorite: v })} options={PRIORITES} vide={null} />
        </Modal>
      )}
    </div>
  );
}
