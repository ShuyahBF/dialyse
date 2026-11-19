// Maintenance des postes de dialyse : état par poste (compteur de séances depuis la dernière préventive), interventions à planifier, démarrer, terminer (coût, durée), annuler.
import { Ban, Check, Play, Plus, RefreshCw, Save, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { aujourdhui, dateFr, fcfa, nb } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

const COULEUR = { planifiee: "bleu", en_cours: "orange", terminee: "vert", annulee: "gris" };

export default function Maintenance() {
  const { avecToast, toast, utilisateur, rafraichirCompteurs } = useApp();
  const peutEcrire = ["technicien", "admin", "super_admin"].includes(utilisateur.role);
  const [liste, setListe] = useState([]);
  const [etat, setEtat] = useState(null);
  const [listes, setListes] = useState({ types: [] });
  const [modal, setModal] = useState(null);
  const [form, setForm] = useState({});
  const tri = useTri();
  const charger = useCallback(async () => {
    const [l, e, t] = await Promise.all([api("/maintenance"), api("/maintenance/etat"), api("/maintenance/listes")]);
    setListe(l); setEtat(e); setListes(t); rafraichirCompteurs?.();
    return l;
  }, [rafraichirCompteurs]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const agir = async (enCours, action, ok) => { const r = await avecToast(enCours, action, ok); setModal(null); await charger(); return r; };
  const lignes = trierLignes(liste, tri.cle, tri.sens);
  const total = liste.filter((i) => i.statut === "terminee").reduce((s, i) => s + (i.cout || 0), 0);
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><Wrench size={24} className="text-citron" /> Maintenance Des Postes</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation de la maintenance", charger, (l) => `${l.length} intervention(s)`)}>Actualiser</Bouton>
          {peutEcrire && <Bouton icone={Plus} variante="principal" onClick={() => { setForm({ date_prevue: aujourdhui() }); setModal({ type: "planifier" }); }}>Planifier une intervention</Bouton>}
        </div>
      </div>
      <BandeauVersion className="mb-3" />
      {etat?.en_retard.length > 0 && <p className="mb-3 rounded-xl bg-rose-50 p-3 text-sm font-semibold text-rose-800 ring-1 ring-rose-200">{etat.en_retard.length} intervention(s) en retard : {etat.en_retard.map((i) => `${i.poste_nom} (${dateFr(i.date_prevue)})`).join(", ")}</p>}

      <h2 className="mb-2 text-lg font-semibold">État des postes</h2>
      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {etat?.postes.map((p) => (
          <div key={p.poste_id} className={`rounded-2xl border-2 p-3 ${p.statut === "maintenance" ? "border-orange-300 bg-orange-50" : p.statut === "hors_service" ? "border-slate-300 bg-slate-100" : "border-emerald-200 bg-white"}`}>
            <div className="mb-1 flex items-center justify-between"><h3 className="font-semibold">{p.poste_nom}</h3><Pastille couleur={p.statut === "actif" ? "vert" : p.statut === "maintenance" ? "orange" : "gris"}>{p.statut === "actif" ? "En service" : p.statut === "maintenance" ? "En maintenance" : "Hors service"}</Pastille></div>
            <p className="text-xs text-slate-600">Dernière : {p.derniere ? dateFr(p.derniere) : "—"} · Prochaine : <b>{p.prochaine ? dateFr(p.prochaine) : "non planifiée"}</b></p>
            <p className="mt-1 text-xs text-slate-600">{nb(p.seances_depuis_preventive, 0)} séance(s) et {p.jours_depuis_preventive} jour(s) depuis la dernière préventive</p>
            {p.a_prevoir && <p className="mt-1 flex items-center gap-1 text-xs font-semibold text-orange-700">⚠ Maintenance préventive à prévoir (seuil : {etat.seuils.seances} séances ou {etat.seuils.jours} jours)</p>}
          </div>
        ))}
      </div>

      <h2 className="mb-2 text-lg font-semibold">Interventions</h2>
      <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
        <table className="tableau">
          <thead><tr><ThTri cle="date_prevue" tri={tri}>Date prévue</ThTri><ThTri cle="poste_nom" tri={tri}>Poste</ThTri><ThTri cle="type" tri={tri}>Type</ThTri><ThTri cle="prestataire" tri={tri}>Prestataire</ThTri>
            <ThTri cle="statut" tri={tri}>État</ThTri><ThTri cle="cout" tri={tri} numerique>Coût</ThTri>{peutEcrire && <th>Actions</th>}</tr></thead>
          <tbody>
            {lignes.length === 0 && <tr><td colSpan={7} className="py-5 text-center text-slate-500">Aucune intervention.</td></tr>}
            {lignes.map((i) => (
              <tr key={i.id}>
                <td className={`tabular-nums font-medium ${i.en_retard ? "text-rose-700" : "text-emeraude"}`}>{dateFr(i.date_prevue)}{i.en_retard && " ⚠"}</td><td>{i.poste_nom}</td><td>{i.type}</td><td>{i.prestataire || "—"}</td>
                <td><Pastille couleur={COULEUR[i.statut]}>{i.statut_libelle}</Pastille></td><td className="num tabular-nums">{i.statut === "terminee" ? fcfa(i.cout) : "—"}</td>
                {peutEcrire && <td className="whitespace-nowrap">
                  {i.statut === "planifiee" && <BoutonIcone icone={Play} libelle="Démarrer : le poste passe en maintenance" couleur="text-orange-600" onClick={() => agir("Démarrage", () => api(`/maintenance/${i.id}/demarrer`, { methode: "POST", corps: {} }), (r) => `Poste en maintenance${r.seances_a_deplacer ? ` : ${r.seances_a_deplacer} séance(s) du jour à déplacer` : ""}`)} />}
                  {["planifiee", "en_cours"].includes(i.statut) && <BoutonIcone icone={Check} libelle="Terminer" couleur="text-emerald-600" onClick={() => { setForm({ date_realisee: aujourdhui(), cout: "", duree_h: "", notes: i.notes || "" }); setModal({ type: "terminer", i }); }} />}
                  {["planifiee", "en_cours"].includes(i.statut) && <BoutonIcone icone={Ban} libelle="Annuler" couleur="text-rose-600" onClick={() => agir("Annulation", () => api(`/maintenance/${i.id}/annuler`, { methode: "POST", corps: {} }), () => "Intervention annulée")} />}
                </td>}
              </tr>
            ))}
          </tbody>
          <tfoot><tr className="font-semibold"><td>Total · {lignes.length} intervention(s)</td><td /><td /><td /><td /><td className="num tabular-nums">{fcfa(total)}</td>{peutEcrire && <td />}</tr></tfoot>
        </table>
      </div>

      {modal?.type === "planifier" && (
        <Modal titre="Planifier une intervention" onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={Save} variante="principal" disabled={!form.poste_id || !form.type || !form.date_prevue} onClick={() => agir("Planification", () => api("/maintenance", { methode: "POST", corps: form }), () => "Intervention planifiée (visible au calendrier)")}>Planifier</Bouton></>}>
          <Liste libelle="Poste" valeur={form.poste_id} onChange={(v) => setForm({ ...form, poste_id: v })} options={(etat?.postes || []).map((p) => ({ valeur: p.poste_id, libelle: p.poste_nom }))} />
          <Liste libelle="Type d'intervention" valeur={form.type} onChange={(v) => setForm({ ...form, type: v })} options={listes.types} />
          <Texte libelle="Date prévue" type="date" valeur={form.date_prevue} onChange={(v) => setForm({ ...form, date_prevue: v })} />
          <Texte libelle="Prestataire (facultatif)" valeur={form.prestataire} onChange={(v) => setForm({ ...form, prestataire: v })} />
          <Texte libelle="Notes (facultatif)" valeur={form.notes} onChange={(v) => setForm({ ...form, notes: v })} />
        </Modal>
      )}
      {modal?.type === "terminer" && (
        <Modal titre={`Terminer — ${modal.i.poste_nom}`} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={Check} variante="vert" onClick={() => agir("Clôture", () => api(`/maintenance/${modal.i.id}/terminer`, { methode: "POST", corps: { ...form, cout: Number(form.cout) || 0, duree_h: form.duree_h === "" ? null : Number(form.duree_h) } }), () => "Intervention terminée : poste remis en service")}>Terminer</Bouton></>}>
          <Texte libelle="Date de réalisation" type="date" valeur={form.date_realisee} onChange={(v) => setForm({ ...form, date_realisee: v })} />
          <Texte libelle="Coût (FCFA)" type="number" valeur={form.cout} onChange={(v) => setForm({ ...form, cout: v })} aide="Pièces et main-d'œuvre : sert au calcul de rentabilité." />
          <Texte libelle="Durée (heures)" type="number" valeur={form.duree_h} onChange={(v) => setForm({ ...form, duree_h: v })} />
          <Texte libelle="Notes" valeur={form.notes} onChange={(v) => setForm({ ...form, notes: v })} />
        </Modal>
      )}
    </div>
  );
}
