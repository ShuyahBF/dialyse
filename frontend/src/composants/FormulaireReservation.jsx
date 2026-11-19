// Fenêtre de réservation d'une place : patient, date, créneau, poste (facultatif), motif ; « Confirmer tout de suite » crée la séance au calendrier.
import { CalendarPlus } from "lucide-react";
import { useEffect, useState } from "react";
import Bouton from "./Bouton.jsx";
import { Liste, Texte } from "./Champs.jsx";
import Modal from "./Modal.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";

const MOTIFS = ["Séance supplémentaire", "Rattrapage d'une séance manquée", "Nouvelle admission", "Patient de passage", "Changement de créneau", "Autre"];

export default function FormulaireReservation({ date, creneau, posteId = "", patientId = "", demandeId = "", motif = "", onFermer, onFait }) {
  const { avecToast, toast } = useApp();
  const [patients, setPatients] = useState([]);
  const [postes, setPostes] = useState([]);
  const [f, setF] = useState({ patient_id: patientId, date: date || "", creneau: creneau || "", poste_id: posteId, motif: motif || "", note: "" });
  useEffect(() => {
    api("/patients?statut=actif").then(setPatients).catch((e) => toast(e.message, "erreur"));
    api("/postes").then((l) => setPostes(l.filter((p) => p.statut === "actif"))).catch(() => {});
  }, [toast]);
  const maj = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const valide = f.patient_id && f.date && f.creneau;
  async function enregistrer(confirmer) {
    const r = await avecToast(confirmer ? "Réservation et confirmation" : "Enregistrement de la réservation",
      () => api("/reservations", { methode: "POST", corps: { ...f, demande_id: demandeId, confirmer, poste_id: confirmer ? f.poste_id : "" } }),
      (r) => (r.statut === "confirmee" ? "Réservation confirmée : séance ajoutée au calendrier" : "Réservation enregistrée (à confirmer)"));
    onFait(r);
  }
  return (
    <Modal titre="Réserver une place" onFermer={onFermer} pied={<><Bouton onClick={onFermer}>Annuler</Bouton>
      <Bouton icone={CalendarPlus} disabled={!valide} onClick={() => enregistrer(false)}>Enregistrer la demande</Bouton>
      <Bouton icone={CalendarPlus} variante="principal" disabled={!valide || !f.poste_id} onClick={() => enregistrer(true)}>Confirmer tout de suite</Bouton></>}>
      <Liste libelle="Patient" valeur={f.patient_id} onChange={(v) => maj("patient_id", v)} options={patients.map((p) => ({ valeur: p.id, libelle: `${p.nom} ${p.prenom} (${p.code})` }))} />
      <div className="grid grid-cols-2 gap-2">
        <Texte libelle="Date" type="date" valeur={f.date} onChange={(v) => maj("date", v)} />
        <Liste libelle="Créneau" valeur={f.creneau} onChange={(v) => maj("creneau", v)} options={["matin", "midi", "soir"]} />
      </div>
      <Liste libelle="Poste" valeur={f.poste_id} onChange={(v) => maj("poste_id", v)} options={postes.map((p) => ({ valeur: p.id, libelle: p.nom }))} vide="— À choisir à la confirmation —" aide="Obligatoire pour « Confirmer tout de suite »." />
      <Liste libelle="Motif" valeur={f.motif} onChange={(v) => maj("motif", v)} options={MOTIFS} />
      <Texte libelle="Note (facultatif)" valeur={f.note} onChange={(v) => maj("note", v)} />
    </Modal>
  );
}
