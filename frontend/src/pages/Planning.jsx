// Planning des séances : grille postes × créneaux pour un jour, planification d'une séance, génération du planning depuis les prescriptions.
import { AlertTriangle, CalendarPlus, ChevronLeft, ChevronRight, Plus, RefreshCw, Wand2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import Bouton from "../composants/Bouton.jsx";
import { Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { ajouterJours, aujourdhui, dateFr } from "../lib/format.js";
import SeanceModal from "./SeanceModal.jsx";

const CRENEAUX = [["matin", "Matin"], ["midi", "Midi"], ["soir", "Soir"]];
export const COULEUR_SEANCE = { planifiee: "bleu", en_cours: "orange", terminee: "vert", annulee: "gris", absente: "rouge" };
const JOURS = ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"];

export default function Planning() {
  const { utilisateur, avecToast, toast } = useApp();
  const peutPlanifier = ["secretariat", "medecin", "infirmier", "admin", "super_admin"].includes(utilisateur.role);
  const [jour, setJour] = useState(aujourdhui());
  const [postes, setPostes] = useState([]);
  const [seances, setSeances] = useState([]);
  const [patients, setPatients] = useState([]);
  const [planif, setPlanif] = useState(null);         // { poste, creneau, patient_id }
  const [gen, setGen] = useState(null);                // { du, au, resultat? }
  const [ouverte, setOuverte] = useState(null);

  const charger = useCallback(async () => {
    const [po, se] = await Promise.all([api("/postes"), api(`/seances?date_=${jour}`)]);
    setPostes(po.filter((p) => p.statut !== "hors_service")); setSeances(se);
  }, [jour]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  useEffect(() => { if (peutPlanifier) api("/patients?statut=actif").then(setPatients).catch(() => {}); }, [peutPlanifier]);

  const dans = (poste, creneau) => seances.find((s) => s.poste_id === poste.id && s.creneau === creneau && !["annulee", "absente"].includes(s.statut));
  const ratees = seances.filter((s) => ["annulee", "absente"].includes(s.statut));

  async function planifier() {
    const r = await avecToast("Planification", () => api("/seances", { methode: "POST", corps: { patient_id: planif.patient_id, poste_id: planif.poste.id, date: jour, creneau: planif.creneau } }), () => "Séance planifiée");
    (r.alertes_planification || []).forEach((a) => toast("⚠ " + a, "erreur"));
    setPlanif(null); await charger();
  }
  async function generer() {
    const r = await avecToast("Génération du planning", () => api("/seances/generer", { methode: "POST", corps: { du: gen.du, au: gen.au } }),
      (x) => `${x.creees} séance(s) créée(s), ${x.deja_existantes} déjà existante(s), ${x.non_placees.length} non placée(s)`);
    setGen({ ...gen, resultat: r }); await charger();
  }
  const d = new Date(jour + "T12:00:00");
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h1 className="text-2xl font-semibold">Planning Des Séances</h1>
        <div className="flex flex-wrap gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation du planning", charger, () => "Planning actualisé")}>Actualiser</Bouton>
          {peutPlanifier && <Bouton icone={Wand2} variante="orange" onClick={() => setGen({ du: jour, au: ajouterJours(jour, 6) })}>Générer le planning</Bouton>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Bouton icone={ChevronLeft} onClick={() => setJour(ajouterJours(jour, -1))} aria-label="Jour précédent" petit>Précédent</Bouton>
        <input type="date" value={jour} onChange={(e) => e.target.value && setJour(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-1.5" />
        <Bouton icone={ChevronRight} onClick={() => setJour(ajouterJours(jour, 1))} petit>Suivant</Bouton>
        <Bouton onClick={() => setJour(aujourdhui())} petit icone={CalendarPlus}>Aujourd'hui</Bouton>
        <span className="font-medium text-emeraude">{JOURS[d.getDay()]} {dateFr(jour)}</span>
      </div>
      <div className="overflow-x-auto rounded-xl ring-1 ring-encre/10 bg-white">
        <table className="tableau">
          <thead><tr><th>Poste</th>{CRENEAUX.map(([k, l]) => <th key={k}>{l}</th>)}</tr></thead>
          <tbody>
            {postes.map((po) => (
              <tr key={po.id}>
                <td className="whitespace-nowrap align-top">
                  <div className="font-semibold text-emeraude">{po.nom}</div>
                  <div className="text-xs text-slate-500">{po.salle}</div>
                  {po.isolement && <Pastille couleur="violet">Isolement</Pastille>}
                  {po.statut === "maintenance" && <Pastille couleur="orange">Maintenance</Pastille>}
                </td>
                {CRENEAUX.map(([k]) => {
                  const s = dans(po, k);
                  return (
                    <td key={k} className="align-top min-w-[11rem]">
                      {s ? (
                        <button onClick={() => setOuverte(s.id)} className="w-full text-left rounded-lg ring-1 ring-encre/10 bg-slate-50 hover:bg-white px-2.5 py-2">
                          <div className="font-medium flex items-center gap-1">{s.patient.nom} {s.patient.prenom}
                            {s.alertes?.some((a) => a.niveau === "critique") && <AlertTriangle size={14} className="text-rose-600" aria-label="Alerte critique" />}
                            {s.serologie_positive && <span title="Sérologie positive" className="text-rose-600 text-xs font-bold">●</span>}</div>
                          <div className="mt-1"><Pastille couleur={COULEUR_SEANCE[s.statut]}>{s.statut_libelle}</Pastille></div>
                        </button>
                      ) : peutPlanifier && po.statut === "actif" ? (
                        <button onClick={() => setPlanif({ poste: po, creneau: k, patient_id: "" })} className="w-full rounded-lg border border-dashed border-slate-300 py-2 text-slate-500 hover:bg-sky-50 inline-flex items-center justify-center gap-1 text-sm">
                          <Plus size={15} /> Planifier
                        </button>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!postes.length && <tr><td colSpan={4} className="text-center text-slate-500 py-6">Aucun poste : créez-les dans « Postes De Dialyse ».</td></tr>}
          </tbody>
        </table>
      </div>
      {ratees.length > 0 && <p className="text-sm text-slate-600 mt-3">Annulées / absents ce jour : {ratees.map((s) => `${s.patient.nom} ${s.patient.prenom} (${s.statut_libelle.toLowerCase()})`).join(", ")}.</p>}

      {planif && (
        <Modal titre={`Planifier — ${planif.poste.nom}, ${planif.creneau}`} onFermer={() => setPlanif(null)}
          pied={<><Bouton onClick={() => setPlanif(null)}>Annuler</Bouton><Bouton icone={CalendarPlus} variante="principal" disabled={!planif.patient_id} onClick={planifier}>Planifier</Bouton></>}>
          <p className="text-sm text-slate-600 mb-3">{dateFr(jour)}</p>
          <Liste libelle="Patient en dialyse" valeur={planif.patient_id} onChange={(v) => setPlanif({ ...planif, patient_id: v })}
            options={patients.map((p) => ({ valeur: p.id, libelle: `${p.nom} ${p.prenom} (${p.code})` }))} />
        </Modal>
      )}
      {gen && (
        <Modal titre="Générer le planning" onFermer={() => setGen(null)}
          pied={<><Bouton onClick={() => setGen(null)}>Fermer</Bouton><Bouton icone={Wand2} variante="orange" onClick={generer}>Générer</Bouton></>}>
          <p className="text-sm text-slate-600 mb-3">Crée les séances de la période d'après les jours et le créneau prescrits à chaque patient actif. Les séances existantes sont conservées ; un patient à sérologie positive n'est placé que sur un poste d'isolement.</p>
          <Texte libelle="Du" type="date" valeur={gen.du} onChange={(v) => setGen({ ...gen, du: v })} />
          <Texte libelle="Au (31 jours au plus)" type="date" valeur={gen.au} onChange={(v) => setGen({ ...gen, au: v })} />
          {gen.resultat && (
            <div className="rounded-lg bg-slate-50 p-3 text-sm">
              <p className="font-medium">{gen.resultat.creees} créée(s) · {gen.resultat.deja_existantes} déjà existante(s)</p>
              {gen.resultat.non_placees.length > 0 && (
                <ul className="mt-2 text-rose-800 list-disc pl-5">{gen.resultat.non_placees.map((n, i) => <li key={i}>{n.patient} — {dateFr(n.date)} {n.creneau} : {n.raison}</li>)}</ul>
              )}
            </div>
          )}
        </Modal>
      )}
      {ouverte && <SeanceModal id={ouverte} onFermer={() => setOuverte(null)} onChange={charger} />}
    </div>
  );
}
