// Rapports d'activité : jour / semaine / mois, période libre, genre et tranches d'âge. Tout est AGRÉGÉ (aucun nom de patient).
import { Activity, CalendarRange, FileText, RefreshCw, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import Bouton from "../composants/Bouton.jsx";
import { Liste, Texte } from "../composants/Champs.jsx";
import PdfInterne from "../composants/PdfInterne.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { ajouterJours, aujourdhui, dateFr, nb } from "../lib/format.js";

const REGROUPEMENTS = [{ valeur: "jour", libelle: "Par jour" }, { valeur: "semaine", libelle: "Par semaine" }, { valeur: "mois", libelle: "Par mois" }];

/** Bornes des périodes prédéfinies (semaine = du lundi au dimanche). */
function preset(nom) {
  const auj = aujourdhui();
  const d = new Date(auj + "T12:00:00");
  const lundi = ajouterJours(auj, -((d.getDay() + 6) % 7));
  const debutMois = auj.slice(0, 8) + "01";
  if (nom === "jour") return [auj, auj, "jour"];
  if (nom === "semaine") return [lundi, ajouterJours(lundi, 6), "jour"];
  if (nom === "mois") return [debutMois, auj, "jour"];
  if (nom === "mois_precedent") { const fin = ajouterJours(debutMois, -1); return [fin.slice(0, 8) + "01", fin, "jour"]; }
  return [ajouterJours(auj, -364), auj, "mois"];                                   // 12 derniers mois
}
const libellePeriode = (p, r) => (r === "mois" ? p : r === "semaine" ? "Sem. " + dateFr(p).slice(0, 5) : dateFr(p).slice(0, 5));

/** Barres verticales (une par période) : la valeur est au-dessus de la barre. */
function Barres({ donnees, regroupement }) {
  const max = Math.max(1, ...donnees.map((d) => d.realisees));
  return (
    <div className="flex items-end gap-1.5 h-40 overflow-x-auto pb-1">
      {donnees.map((d) => (
        <div key={d.periode} className="flex flex-col items-center justify-end h-full min-w-[2.2rem] flex-1">
          <span className="text-[11px] tabular-nums">{d.realisees}</span>
          <div className="w-full rounded-t bg-turquoise-500" style={{ height: `${(d.realisees / max) * 100}%`, minHeight: d.realisees ? 3 : 1 }} title={`${d.periode} : ${d.realisees} séance(s), ${d.patients} patient(s)`} />
          <span className="text-[10px] text-slate-500 mt-1 whitespace-nowrap">{libellePeriode(d.periode, regroupement)}</span>
        </div>
      ))}
    </div>
  );
}

/** Barre horizontale proportionnelle à `valeur` / `max`. */
const Ligne = ({ etiquette, valeur, max, couleur = "bg-turquoise-500", suffixe = "" }) => (
  <div className="flex items-center gap-2 text-sm mb-1.5">
    <span className="w-28 shrink-0">{etiquette}</span>
    <div className="flex-1 h-4 rounded bg-slate-100"><div className={`h-4 rounded ${couleur}`} style={{ width: `${max ? (valeur / max) * 100 : 0}%` }} /></div>
    <span className="w-24 shrink-0 whitespace-nowrap text-right tabular-nums">{valeur}{suffixe}</span>
  </div>
);

const Carte = ({ titre, valeur, sous, couleur = "text-nuit" }) => (
  <div className="rounded-xl bg-white ring-1 ring-encre/10 p-3"><div className="text-sm text-slate-500">{titre}</div><div className={`text-2xl font-semibold tabular-nums ${couleur}`}>{valeur}</div>{sous && <div className="text-xs text-slate-500">{sous}</div>}</div>
);

export default function Rapports() {
  const { avecToast, toast } = useApp();
  const [[du, au, regroupement], setP] = useState(preset("mois"));
  const [r, setR] = useState(null);
  const [pdf, setPdf] = useState(false);
  const charger = useCallback(async () => setR(await api(`/rapports/activite?du=${du}&au=${au}&regroupement=${regroupement}`)), [du, au, regroupement]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const t = r?.totaux;
  const d = r?.demographie;
  const maxTr = Math.max(1, ...(d?.tranches || []).map((x) => x.seances));
  const maxGenre = Math.max(1, ...(d?.genre || []).map((x) => x.seances));
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h1 className="text-2xl font-semibold">Rapports</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation du rapport", charger, () => "Rapport actualisé")}>Actualiser</Bouton>
          <Bouton icone={FileText} variante="principal" onClick={() => setPdf(true)}>Afficher le PDF</Bouton>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 mb-3">
        {[["jour", "Aujourd'hui"], ["semaine", "Cette semaine"], ["mois", "Ce mois"], ["mois_precedent", "Mois précédent"], ["annee", "12 derniers mois"]].map(([k, l]) => (
          <Bouton key={k} petit icone={CalendarRange} onClick={() => setP(preset(k))}>{l}</Bouton>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <div><Texte libelle="Du" type="date" valeur={du} onChange={(v) => v && setP([v, au, regroupement])} /></div>
        <div><Texte libelle="Au" type="date" valeur={au} onChange={(v) => v && setP([du, v, regroupement])} /></div>
        <div className="min-w-[10rem]"><Liste libelle="Regroupement" valeur={regroupement} vide="" onChange={(v) => setP([du, au, v])} options={REGROUPEMENTS} /></div>
      </div>
      {!r ? <span className="jauge" /> : <>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <Carte titre="Séances réalisées" valeur={t.realisees} sous={`${t.planifiees} planifiée(s) · ${t.annulees} annulée(s)`} />
          <Carte titre="Patients traités" valeur={t.patients} sous={`${r.patients_actifs} patients actifs au total`} />
          <Carte titre="Taux d'absence" valeur={`${nb(t.taux_absence_pct)} %`} sous={`${t.absents} séance(s) manquée(s)`} couleur={t.taux_absence_pct > 10 ? "text-orange-700" : "text-emerald-700"} />
          <Carte titre="Kt/V moyen" valeur={t.ktv_moyen != null ? nb(t.ktv_moyen, 2) : "—"} sous={t.ktv_conforme_pct != null ? `${nb(t.ktv_conforme_pct)} % des séances ≥ 1,2` : "pas de mesure"} couleur={t.ktv_moyen != null && t.ktv_moyen < 1.2 ? "text-rose-700" : "text-nuit"} />
          <Carte titre="Durée moyenne" valeur={t.duree_moyenne_min != null ? `${nb(t.duree_moyenne_min, 0)} min` : "—"} />
          <Carte titre="Ultrafiltration moyenne" valeur={t.uf_moyenne_l != null ? `${nb(t.uf_moyenne_l, 2)} l` : "—"} />
          <Carte titre="Incidents déclarés" valeur={t.incidents} couleur={t.incidents ? "text-orange-700" : "text-nuit"} />
        </div>
        <section className="rounded-2xl bg-white p-4 ring-1 ring-encre/10 mb-4">
          <h2 className="font-semibold mb-3 flex items-center gap-2"><Activity size={18} className="text-turquoise-600" /> Séances réalisées ({REGROUPEMENTS.find((x) => x.valeur === regroupement).libelle.toLowerCase()})</h2>
          {r.serie.length ? <Barres donnees={r.serie} regroupement={regroupement} /> : <p className="text-sm text-slate-500">Aucune séance sur la période.</p>}
        </section>
        <div className="grid lg:grid-cols-2 gap-4 mb-4">
          <section className="rounded-2xl bg-white p-4 ring-1 ring-encre/10">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Users size={18} className="text-violet-600" /> Par genre</h2>
            {d.genre.map((g) => <Ligne key={g.genre} etiquette={g.libelle} valeur={g.seances} max={maxGenre} couleur={g.genre === "F" ? "bg-pink-400" : g.genre === "M" ? "bg-sky-500" : "bg-slate-400"} suffixe={` (${g.patients} pat.)`} />)}
            {!d.genre.length && <p className="text-sm text-slate-500">Aucune donnée.</p>}
          </section>
          <section className="rounded-2xl bg-white p-4 ring-1 ring-encre/10">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Users size={18} className="text-violet-600" /> Par tranche d'âge</h2>
            {d.tranches.map((x) => <Ligne key={x.tranche} etiquette={x.tranche} valeur={x.seances} max={maxTr} couleur="bg-violet-400" suffixe={` (${x.patients})`} />)}
            {!d.tranches.length && <p className="text-sm text-slate-500">Aucune donnée.</p>}
          </section>
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <section><h2 className="font-semibold mb-2">Genre × tranche d'âge (patients)</h2>
            <table className="tableau"><thead><tr><th>Tranche</th><th className="num">Femmes</th><th className="num">Hommes</th><th className="num">Kt/V moyen</th></tr></thead>
              <tbody>{d.croise.map((x) => <tr key={x.tranche}><td className="font-medium">{x.tranche}</td><td className="num">{x.femmes}</td><td className="num">{x.hommes}</td><td className="num">{nb(d.tranches.find((y) => y.tranche === x.tranche)?.ktv_moyen, 2)}</td></tr>)}
                {!d.croise.length && <tr><td colSpan={4} className="text-slate-500">Aucune donnée.</td></tr>}</tbody></table></section>
          <section><h2 className="font-semibold mb-2">Par poste et incidents</h2>
            <table className="tableau mb-3"><thead><tr><th>Poste</th><th className="num">Séances</th><th className="num">Absents</th></tr></thead>
              <tbody>{r.par_poste.map((x) => <tr key={x.poste}><td className="font-medium">{x.poste}</td><td className="num">{x.realisees}</td><td className="num">{x.absents}</td></tr>)}
                {!r.par_poste.length && <tr><td colSpan={3} className="text-slate-500">Aucune donnée.</td></tr>}</tbody></table>
            {r.incidents.length > 0 && <table className="tableau"><thead><tr><th>Incident</th><th className="num">Nombre</th></tr></thead><tbody>{r.incidents.map((x) => <tr key={x.type}><td>{x.type}</td><td className="num">{x.nombre}</td></tr>)}</tbody></table>}</section>
        </div></>}
      {pdf && <PdfInterne titre={`Rapport du ${dateFr(du)} au ${dateFr(au)}`} chemin={`/rapports/pdf?du=${du}&au=${au}&regroupement=${regroupement}`} onFermer={() => setPdf(false)} />}
    </div>
  );
}
