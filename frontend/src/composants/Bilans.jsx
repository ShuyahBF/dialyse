// Onglet « Bilans » du dossier patient : tableau des bilans (valeurs colorées selon la cible), courbe d'évolution d'un paramètre, saisie d'un bilan.
// Chaque valeur anormale porte un pictogramme ET une couleur (jamais la couleur seule : règle 16).
import { AlertTriangle, ArrowDown, ArrowUp, Plus, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { aujourdhui, dateFr, nb } from "../lib/format.js";
import Bouton from "./Bouton.jsx";
import { Liste, Texte } from "./Champs.jsx";

const STYLE = { normal: "", bas: "text-orange-700 font-medium", haut: "text-orange-700 font-medium", critique_bas: "text-rose-700 font-bold", critique_haut: "text-rose-700 font-bold" };

/** Valeur d'un paramètre avec son pictogramme d'état (flèche = hors cible, triangle = critique). */
function Valeur({ v }) {
  if (!v) return <span className="text-slate-300">—</span>;
  const crit = v.statut.startsWith("critique");
  return (
    <span className={`inline-flex items-center gap-0.5 tabular-nums ${STYLE[v.statut]}`}>
      {crit && <AlertTriangle size={13} aria-label="Valeur critique" />}
      {!crit && v.statut === "bas" && <ArrowDown size={13} aria-label="Sous la cible" />}
      {!crit && v.statut === "haut" && <ArrowUp size={13} aria-label="Au-dessus de la cible" />}
      {nb(v.valeur, 2)}
    </span>
  );
}

/** Courbe d'évolution (SVG) avec bande de la cible ; points rouges si critique, orange si hors cible. */
function Courbe({ serie, param }) {
  if (serie.length < 2) return <p className="text-sm text-slate-500">Au moins deux bilans sont nécessaires pour tracer la courbe.</p>;
  const L = 320, H = 110, m = 24;
  const valeurs = serie.map((s) => s.valeur);
  const bornes = [...valeurs, param?.mini ?? valeurs[0], param?.maxi ?? valeurs[0]];
  const mini = Math.min(...bornes), maxi = Math.max(...bornes), ecart = maxi - mini || 1;
  const x = (i) => m + (i * (L - 2 * m)) / (serie.length - 1);
  const y = (v) => H - m - ((v - mini) / ecart) * (H - 2 * m);
  const bande = param && (param.mini != null || param.maxi != null);
  return (
    <svg viewBox={`0 0 ${L} ${H}`} className="w-full max-w-md" role="img" aria-label={`Évolution : ${param?.libelle || "URR"}`}>
      {bande && <rect x={m} width={L - 2 * m} y={y(param.maxi ?? maxi)} height={Math.max(2, y(param.mini ?? mini) - y(param.maxi ?? maxi))} fill="#bbf7d0" opacity="0.6" />}
      <polyline fill="none" stroke="#0e7490" strokeWidth="2" points={serie.map((s, i) => `${x(i)},${y(s.valeur)}`).join(" ")} />
      {serie.map((s, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(s.valeur)} r="4" fill={s.statut.startsWith("critique") ? "#e11d48" : s.statut === "normal" ? "#0e7490" : "#f97316"} />
          <text x={x(i)} y={y(s.valeur) - 7} fontSize="9" textAnchor="middle" fill="#0A1E3D">{nb(s.valeur, 1)}</text>
          <text x={x(i)} y={H - 6} fontSize="8" textAnchor="middle" fill="#64748b">{dateFr(s.date).slice(0, 5)}</text>
        </g>
      ))}
    </svg>
  );
}

export default function Bilans({ patient, peutEcrire }) {
  const { avecToast, toast } = useApp();
  const [cat, setCat] = useState(null);
  const [bilans, setBilans] = useState(null);
  const [cle, setCle] = useState("potassium");
  const [serie, setSerie] = useState([]);
  const [form, setForm] = useState(null);                 // null = fermé ; sinon { date, type, resultats: {}, commentaire }
  const charger = useCallback(async () => setBilans(await api(`/patients/${patient.id}/bilans`)), [patient.id]);
  useEffect(() => { api("/bilans/parametres").then(setCat).catch((e) => toast(e.message, "erreur")); charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  useEffect(() => { api(`/patients/${patient.id}/bilans/evolution/${cle}`).then(setSerie).catch(() => setSerie([])); }, [patient.id, cle, bilans]);
  if (!cat || !bilans) return <span className="jauge" />;

  const presents = cat.parametres.filter((p) => bilans.some((b) => b.resultats[p.cle] !== undefined));
  const param = cat.parametres.find((p) => p.cle === cle);
  const enregistrer = async () => {
    const resultats = Object.fromEntries(Object.entries(form.resultats).filter(([, v]) => v !== ""));
    await avecToast("Enregistrement du bilan", () => api(`/patients/${patient.id}/bilans`, { methode: "POST", corps: { date_prelevement: form.date, type: form.type, resultats, commentaire: form.commentaire } }), () => "Bilan enregistré");
    setForm(null); await charger();
  };
  return (
    <div>
      {peutEcrire && !form && <Bouton icone={Plus} variante="principal" onClick={() => setForm({ date: aujourdhui(), type: "Mensuel", resultats: {}, commentaire: "" })}>Nouveau bilan</Bouton>}
      {form && (
        <div className="rounded-xl bg-slate-50 p-3 mb-4">
          <p className="font-medium mb-2">Nouveau bilan</p>
          <div className="grid grid-cols-2 gap-x-2">
            <Texte libelle="Date du prélèvement" type="date" valeur={form.date} onChange={(v) => setForm({ ...form, date: v })} />
            <Liste libelle="Type" valeur={form.type} onChange={(v) => setForm({ ...form, type: v })} options={cat.types} />
          </div>
          <div className="grid grid-cols-2 gap-x-2">
            {cat.parametres.map((p) => (
              <Texte key={p.cle} libelle={`${p.libelle} (${p.unite})`} type="number" step="0.01" valeur={form.resultats[p.cle] ?? ""}
                onChange={(v) => setForm({ ...form, resultats: { ...form.resultats, [p.cle]: v } })} aide={p.mini != null || p.maxi != null ? `Cible : ${p.mini ?? "…"} – ${p.maxi ?? "…"}` : undefined} />
            ))}
          </div>
          <Texte libelle="Commentaire" valeur={form.commentaire} onChange={(v) => setForm({ ...form, commentaire: v })} />
          <div className="flex gap-2">
            <Bouton onClick={() => setForm(null)}>Annuler</Bouton>
            <Bouton icone={Save} variante="vert" disabled={!form.date || Object.values(form.resultats).every((v) => v === "")} onClick={enregistrer}>Enregistrer le bilan</Bouton>
          </div>
        </div>
      )}
      {!bilans.length ? <p className="text-sm text-slate-500 mt-3">Aucun bilan enregistré.</p> : (
        <>
          <div className="overflow-x-auto rounded-xl border border-slate-200 mt-3">
            <table className="tableau">
              <thead><tr><th>Date</th><th>Type</th>{presents.map((p) => <th key={p.cle} className="num" title={p.unite}>{p.libelle}</th>)}<th className="num">URR %</th></tr></thead>
              <tbody>
                {bilans.map((b) => (
                  <tr key={b.id}>
                    <td className="whitespace-nowrap font-medium text-sky-800">{dateFr(b.date_prelevement)}</td><td>{b.type}</td>
                    {presents.map((p) => <td key={p.cle} className="num"><Valeur v={b.analyse.lignes[p.cle]} /></td>)}
                    <td className={`num ${b.analyse.urr != null && b.analyse.urr < cat.urr_cible ? "text-orange-700 font-medium" : ""}`}>{b.analyse.urr != null ? nb(b.analyse.urr) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4">
            <Liste libelle="Courbe d'évolution" valeur={cle} onChange={setCle} vide="" options={[...cat.parametres.map((p) => ({ valeur: p.cle, libelle: `${p.libelle} (${p.unite})` })), { valeur: "urr", libelle: "URR (%)" }]} />
            <Courbe serie={serie} param={param && cle !== "urr" ? param : cle === "urr" ? { libelle: "URR", mini: cat.urr_cible, maxi: null } : null} />
          </div>
        </>
      )}
    </div>
  );
}
