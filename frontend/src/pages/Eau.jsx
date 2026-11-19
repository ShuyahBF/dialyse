// Contrôle de l'eau de dialyse : relevés (chlore, dureté, conductivité, bactériologie, endotoxines), seuils, non-conformités à traiter (action corrective obligatoire).
// Les seuils sont des valeurs usuelles à valider par le médecin responsable et le technicien biomédical.
import { AlertTriangle, CheckCircle2, Droplets, Plus, RefreshCw, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { aujourdhui, dateFr, nb } from "../lib/format.js";

const COULEUR = { conforme: "vert", alerte: "orange", non_conforme: "rouge" };
const LIB = { conforme: "Conforme", alerte: "À surveiller", non_conforme: "NON CONFORME" };

/** Petite courbe des 30 derniers jours (SVG) avec la limite en pointillé. */
function Courbe({ serie, limite }) {
  if (!serie.length) return <p className="text-xs text-slate-400">Aucun relevé sur 30 jours</p>;
  const max = Math.max(limite * 1.3, ...serie.map((s) => s.valeur));
  const x = (i) => (serie.length === 1 ? 50 : (i / (serie.length - 1)) * 100);
  const y = (v) => 30 - (v / max) * 28;
  return (
    <svg viewBox="0 0 100 32" className="h-10 w-full" role="img" aria-label="Évolution sur 30 jours">
      <line x1="0" x2="100" y1={y(limite)} y2={y(limite)} stroke="#e11d48" strokeDasharray="2 2" strokeWidth="0.6" />
      <polyline fill="none" stroke="#03316E" strokeWidth="1" points={serie.map((s, i) => `${x(i)},${y(s.valeur)}`).join(" ")} />
      {serie.map((s, i) => <circle key={i} cx={x(i)} cy={y(s.valeur)} r="1.4" fill={s.niveau === "non_conforme" ? "#e11d48" : s.niveau === "alerte" ? "#f59e0b" : "#059669"} />)}
    </svg>
  );
}

export default function Eau() {
  const { avecToast, toast, rafraichirCompteurs } = useApp();
  const [etat, setEtat] = useState(null);
  const [liste, setListe] = useState([]);
  const [points, setPoints] = useState([]);
  const [modal, setModal] = useState(null);
  const [form, setForm] = useState({});
  const charger = useCallback(async () => {
    const [e, l, p] = await Promise.all([api("/eau/etat"), api(`/eau/controles?du=${new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10)}`), api("/eau/listes")]);
    setEtat(e); setListe(l); setPoints(p.points); rafraichirCompteurs?.();
    return e;
  }, [rafraichirCompteurs]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const agir = async (enCours, action, ok) => { await avecToast(enCours, action, ok); setModal(null); await charger(); };
  if (!etat) return <div className="flex justify-center py-10"><span className="jauge" /></div>;
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><Droplets size={24} className="text-sky-600" /> Contrôle De L'Eau</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation du contrôle de l'eau", charger, (e) => `${e.manquants} contrôle(s) à faire, ${e.non_traites.length} relevé(s) à traiter`)}>Actualiser</Bouton>
          <Bouton icone={Plus} variante="principal" onClick={() => { setForm({ date: aujourdhui() }); setModal({ type: "releve" }); }}>Nouveau relevé</Bouton>
        </div>
      </div>
      <BandeauVersion className="mb-3" />

      {etat.non_traites.length > 0 && (
        <div className="mb-4 rounded-xl bg-rose-50 p-3 ring-1 ring-rose-200" data-testid="non-conformites">
          <p className="mb-2 flex items-center gap-2 font-semibold text-rose-800"><AlertTriangle size={16} /> {etat.non_traites.length} relevé(s) hors seuil à traiter (action corrective obligatoire)</p>
          <ul className="space-y-1 text-sm">{etat.non_traites.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-2"><Pastille couleur={COULEUR[r.niveau]}>{LIB[r.niveau]}</Pastille><b>{r.libelle}</b> {nb(r.valeur, 3)} {r.unite} · {r.point} · {dateFr(r.date)}
              <Bouton petit onClick={() => { setForm({ action: "" }); setModal({ type: "traiter", r }); }}>Documenter l'action</Bouton></li>))}</ul>
        </div>
      )}

      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {etat.tests.map((t) => (
          <div key={t.cle} className={`rounded-2xl border-2 bg-white p-3 ${t.dernier?.niveau === "non_conforme" ? "border-rose-300" : t.manquant ? "border-orange-300" : "border-emerald-200"}`}>
            <div className="mb-1 flex items-center justify-between gap-2"><h3 className="font-semibold">{t.libelle}</h3>
              {t.dernier ? <Pastille couleur={COULEUR[t.dernier.niveau]}>{LIB[t.dernier.niveau]}</Pastille> : <Pastille>Aucun relevé</Pastille>}</div>
            <p className="text-2xl font-bold tabular-nums text-emeraude">{t.dernier ? nb(t.dernier.valeur, 3) : "—"} <span className="text-sm font-medium text-slate-500">{t.unite}</span></p>
            <p className="text-xs text-slate-500">Limite {nb(t.limite, 3)} · alerte {nb(t.alerte, 3)} · {t.frequence} · {t.point}</p>
            <Courbe serie={t.serie} limite={t.limite} />
            <p className={`mt-1 flex items-center gap-1 text-xs font-semibold ${t.manquant ? "text-orange-700" : "text-emerald-700"}`}>
              {t.manquant ? <><AlertTriangle size={13} /> {t.frequence === "quotidien" ? "À faire aujourd'hui" : "Contrôle mensuel à faire"}</> : <><CheckCircle2 size={13} /> {t.frequence === "quotidien" ? "Fait aujourd'hui" : "À jour"}</>}</p>
          </div>
        ))}
      </div>

      <h2 className="mb-2 text-lg font-semibold">Relevés des 30 derniers jours</h2>
      <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
        <table className="tableau"><thead><tr><th>Date</th><th>Contrôle</th><th>Point</th><th className="num">Valeur</th><th>Niveau</th><th>Action corrective</th><th>Par</th></tr></thead>
          <tbody>
            {liste.length === 0 && <tr><td colSpan={7} className="py-5 text-center text-slate-500">Aucun relevé.</td></tr>}
            {liste.map((r) => (
              <tr key={r.id}><td className="tabular-nums">{dateFr(r.date)}</td><td className="font-medium text-emeraude">{r.libelle}</td><td>{r.point}</td><td className="num tabular-nums">{nb(r.valeur, 3)} {r.unite}</td>
                <td><Pastille couleur={COULEUR[r.niveau]}>{LIB[r.niveau]}</Pastille></td><td className="max-w-xs truncate" title={r.action}>{r.action || (r.traite ? "—" : "à documenter")}</td><td>{r.par}</td></tr>))}
          </tbody></table>
      </div>
      <p className="mt-2 text-xs text-slate-500">Seuils usuels, à valider par le médecin responsable et le technicien biomédical (regroupés dans le serveur, fichier eau.py).</p>

      {modal?.type === "releve" && (
        <Modal titre="Nouveau relevé" onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={Save} variante="principal" disabled={!form.test || form.valeur === undefined || form.valeur === ""} onClick={() => agir("Enregistrement du relevé", () => api("/eau/controles", { methode: "POST", corps: { ...form, valeur: Number(form.valeur) } }), () => "Relevé enregistré")}>Enregistrer</Bouton></>}>
          <Liste libelle="Contrôle" valeur={form.test} onChange={(v) => setForm({ ...form, test: v, point: etat.tests.find((t) => t.cle === v)?.point })} options={etat.tests.map((t) => ({ valeur: t.cle, libelle: `${t.libelle} (${t.unite})` }))} />
          <Texte libelle="Valeur mesurée" type="number" step="any" valeur={form.valeur} onChange={(v) => setForm({ ...form, valeur: v })} />
          <Liste libelle="Point de prélèvement" valeur={form.point} onChange={(v) => setForm({ ...form, point: v })} options={points} vide={null} />
          <Texte libelle="Date" type="date" valeur={form.date} onChange={(v) => setForm({ ...form, date: v })} />
          <Texte libelle="Note (facultatif)" valeur={form.note} onChange={(v) => setForm({ ...form, note: v })} />
        </Modal>
      )}
      {modal?.type === "traiter" && (
        <Modal titre={`Action corrective — ${modal.r.libelle}`} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={Save} variante="principal" disabled={!form.action} onClick={() => agir("Enregistrement", () => api(`/eau/controles/${modal.r.id}/traiter`, { methode: "PUT", corps: form }), () => "Action corrective enregistrée")}>Enregistrer</Bouton></>}>
          <p className="mb-2 text-sm">{nb(modal.r.valeur, 3)} {modal.r.unite} · {modal.r.point} · {dateFr(modal.r.date)}</p>
          <Texte libelle="Action corrective menée" valeur={form.action} onChange={(v) => setForm({ action: v })} placeholder="Rinçage des membranes, nouveau relevé conforme" />
        </Modal>
      )}
    </div>
  );
}
