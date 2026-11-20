// Rentabilité du centre : recettes, coûts (personnel, maintenance, charges saisies), marge, coût et recette par séance, seuil de rentabilité ; totaux sous le tableau (règle 25).
import { AlertTriangle, Plus, RefreshCw, Save, Trash2, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Liste, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { fcfa, nb } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

const NOMS_MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const libMois = (m) => `${NOMS_MOIS[Number(m.slice(5)) - 1]} ${m.slice(0, 4)}`;
const COLONNES = [["seances", "Séances", "n"], ["facture", "Facturé", "f"], ["encaisse", "Encaissé", "f"], ["personnel", "Personnel", "f"], ["maintenance", "Maintenance", "f"], ["charges", "Charges", "f"], ["consommables_stock", "Conso. stock", "f"],
                  ["couts", "Coûts", "f"], ["marge", "Marge", "f"], ["taux_marge_pct", "Marge %", "p"], ["cout_par_seance", "Coût / séance", "f"], ["recette_par_seance", "Recette / séance", "f"], ["seuil_seances", "Seuil (séances)", "n"]];
const fmt = (v, t) => (v === null || v === undefined ? "—" : t === "f" ? fcfa(v) : t === "p" ? nb(v) + " %" : nb(v, 0));

export default function Rentabilite() {
  const { avecToast, toast, utilisateur } = useApp();
  const peutSaisir = ["admin", "super_admin"].includes(utilisateur.role);
  const aujMois = new Date().toISOString().slice(0, 7);
  const debutDefaut = (() => { const d = new Date(); d.setMonth(d.getMonth() - 5); return d.toISOString().slice(0, 7); })();
  const [de, setDe] = useState(debutDefaut);
  const [a, setA] = useState(aujMois);
  const [r, setR] = useState(null);
  const [charges, setCharges] = useState([]);
  const [cats, setCats] = useState([]);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({});
  const tri = useTri();
  const charger = useCallback(async () => {
    const [x, c, l] = await Promise.all([api(`/rentabilite?de=${de}&a=${a}`), api(`/rentabilite/charges`), api("/rentabilite/listes")]);
    setR(x); setCharges(c.filter((y) => y.mois >= de && y.mois <= a)); setCats(l.categories);
    return x;
  }, [de, a]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  if (!r) return <div className="flex justify-center py-10"><span className="jauge" /></div>;
  const lignes = trierLignes(r.mois, tri.cle, tri.sens);
  const t = r.total;
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><TrendingUp size={24} className="text-emerald-600" /> Rentabilité</h1>
        <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation de la rentabilité", charger, (x) => `Rentabilité de ${x.mois.length} mois actualisée`)}>Actualiser</Bouton>
      </div>
      <BandeauVersion className="mb-3" />
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Texte libelle="De (mois)" type="month" valeur={de} onChange={setDe} /><Texte libelle="À (mois)" type="month" valeur={a} onChange={setA} />
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[["Facturé", fcfa(t.facture), "text-emeraude"], ["Coûts", fcfa(t.couts), "text-ardoise"], ["Marge", fcfa(t.marge), t.marge >= 0 ? "text-emerald-700" : "text-rose-700"], ["Seuil de rentabilité", t.seuil_seances ? `${nb(t.seuil_seances, 0)} séances / mois` : "—", "text-encre"]].map(([l, v, c]) => (
          <div key={l} className="rounded-2xl bg-white p-3 ring-1 ring-encre/5"><p className="text-xs text-ardoise">{l}</p><p className={`text-lg font-bold tabular-nums ${c}`}>{v}</p></div>))}
      </div>
      <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
        <table className="tableau" data-sans-defilement>
          <thead><tr><ThTri cle="mois" tri={tri}>Mois</ThTri>{COLONNES.map(([k, l]) => <ThTri key={k} cle={k} tri={tri} numerique>{l}</ThTri>)}</tr></thead>
          <tbody>{lignes.map((l) => <tr key={l.mois}><td className="font-medium text-emeraude">{libMois(l.mois)}</td>{COLONNES.map(([k, , ty]) => <td key={k} className={`num tabular-nums ${k === "marge" ? (l.marge >= 0 ? "text-emerald-700" : "font-semibold text-rose-700") : ""}`}>{fmt(l[k], ty)}</td>)}</tr>)}</tbody>
          <tfoot><tr className="font-semibold"><td>Total · {lignes.length} mois</td>{COLONNES.map(([k, , ty]) => <td key={k} className="num tabular-nums">{fmt(t[k], ty)}</td>)}</tr></tfoot>
        </table>
      </div>
      {t.conso_sans_prix > 0 && (
        <p className="mt-2 flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-900" data-testid="alerte-sans-prix">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span><b>{nb(t.conso_sans_prix, 2)} unité(s)</b> sorties du stock sur la période viennent de lots sans prix : elles ne sont pas comptées dans « Conso. stock ». Renseignez le prix unitaire à la réception des lots (écran Consommables et stocks).</span>
        </p>
      )}
      <p className="mt-2 text-xs text-slate-500">« Conso. stock » = sorties et pertes de stock du mois × prix unitaire du lot : ne saisissez plus à la main, pour ces mois, la charge « Consommables et médicaments » correspondante (elle serait comptée deux fois). Coûts = personnel (coût mensuel des salariés actifs) + maintenance (interventions terminées) + charges saisies. Variables = consommables et médicaments ; fixes = le reste. Seuil = coûts fixes / (recette moyenne − coût variable moyen par séance). Les pourcentages ne sont jamais additionnés.</p>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">Charges saisies</h2>
        {peutSaisir && <Bouton icone={Plus} onClick={() => { setForm({ mois: a, categorie: "" }); setModal(true); }}>Ajouter une charge</Bouton>}</div>
      <div className="mt-2 overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
        <table className="tableau"><thead><tr><th>Mois</th><th>Catégorie</th><th className="num">Montant</th><th>Note</th>{peutSaisir && <th>Actions</th>}</tr></thead>
          <tbody>
            {charges.length === 0 && <tr><td colSpan={5} className="py-5 text-center text-slate-500">Aucune charge saisie sur la période.</td></tr>}
            {charges.map((c) => <tr key={c.id}><td>{libMois(c.mois)}</td><td>{c.categorie}</td><td className="num tabular-nums">{fcfa(c.montant)}</td><td>{c.note || "—"}</td>
              {peutSaisir && <td><BoutonIcone icone={Trash2} libelle="Supprimer la charge" couleur="text-rose-600" onClick={() => avecToast("Suppression", () => api(`/rentabilite/charges/${c.id}`, { methode: "DELETE" }), () => "Charge supprimée").then(charger)} /></td>}</tr>)}
          </tbody>
          <tfoot><tr className="font-semibold"><td>Total · {charges.length} ligne(s)</td><td /><td className="num tabular-nums">{fcfa(charges.reduce((s, c) => s + c.montant, 0))}</td><td />{peutSaisir && <td />}</tr></tfoot></table>
      </div>
      {modal && (
        <Modal titre="Ajouter une charge" onFermer={() => setModal(false)} pied={<><Bouton onClick={() => setModal(false)}>Annuler</Bouton>
          <Bouton icone={Save} variante="principal" disabled={!form.categorie || !form.montant} onClick={async () => { await avecToast("Enregistrement", () => api("/rentabilite/charges", { methode: "POST", corps: { ...form, montant: Number(form.montant) } }), () => "Charge enregistrée"); setModal(false); await charger(); }}>Enregistrer</Bouton></>}>
          <Texte libelle="Mois" type="month" valeur={form.mois} onChange={(v) => setForm({ ...form, mois: v })} />
          <Liste libelle="Catégorie" valeur={form.categorie} onChange={(v) => setForm({ ...form, categorie: v })} options={cats.map((c) => ({ valeur: c.valeur, libelle: c.valeur + (c.variable ? " (variable)" : "") }))} />
          <Texte libelle="Montant (FCFA)" type="number" valeur={form.montant} onChange={(v) => setForm({ ...form, montant: v })} />
          <Texte libelle="Note (facultatif)" valeur={form.note} onChange={(v) => setForm({ ...form, note: v })} />
        </Modal>
      )}
    </div>
  );
}
