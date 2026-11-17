// Tableau de bord : séances du jour par statut, occupation des postes, patients, incidents, séances sur 6 mois. Bouton « Actualiser » (règle 17).
import { Activity, AlertTriangle, CalendarCheck, FlaskConical, Monitor, RefreshCw, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import Bouton from "../composants/Bouton.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateFr } from "../lib/format.js";

const COULEURS = { planifiee: "bg-sky-500", en_cours: "bg-orange-500", terminee: "bg-emerald-600", annulee: "bg-slate-400", absente: "bg-rose-500" };
const LIBELLES = { planifiee: "Planifiées", en_cours: "En cours", terminee: "Terminées", annulee: "Annulées", absente: "Absents" };

function Carte({ icone: Icone, titre, valeur, sous, couleur }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm border border-slate-200">
      <div className={`inline-flex rounded-xl p-2 mb-2 ${couleur}`}><Icone size={20} /></div>
      <div className="text-2xl font-semibold tabular-nums">{valeur}</div>
      <div className="text-sm text-slate-600">{titre}</div>
      {sous && <div className="text-xs text-slate-500 mt-0.5">{sous}</div>}
    </div>
  );
}

export default function Tableau() {
  const { avecToast, toast } = useApp();
  const [t, setT] = useState(null);
  const [suivi, setSuivi] = useState(null);
  // Deux lectures indépendantes lancées en parallèle (règle 7) : indicateurs et suivi des bilans.
  const charger = useCallback(async () => { const [x, s] = await Promise.all([api("/tableau"), api("/bilans/suivi")]); setT(x); setSuivi(s); }, []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const actualiser = () => avecToast("Actualisation du tableau de bord", charger, () => "Tableau de bord actualisé");
  if (!t) return <div className="p-8 flex justify-center"><span className="jauge" /></div>;
  const max = Math.max(1, ...t.seances_par_mois.map((m) => m.nombre));
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h1 className="text-2xl font-semibold">Tableau De Bord <span className="text-base font-normal text-slate-500">— {dateFr(t.date)}</span></h1>
        <Bouton icone={RefreshCw} onClick={actualiser}>Actualiser</Bouton>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <Carte icone={CalendarCheck} titre="Séances aujourd'hui" valeur={t.seances_jour.total} couleur="bg-sky-100 text-sky-700" />
        <Carte icone={Activity} titre="Occupation des postes" valeur={t.occupation_pct + " %"} sous={`${t.postes.en_service} poste(s) en service sur ${t.postes.total}`} couleur="bg-emerald-100 text-emerald-700" />
        <Carte icone={Users} titre="Patients en dialyse" valeur={t.patients_actifs} couleur="bg-violet-100 text-violet-700" />
        <Carte icone={AlertTriangle} titre="Incidents ce mois-ci" valeur={t.incidents_mois} couleur={t.incidents_mois ? "bg-orange-100 text-orange-700" : "bg-slate-100 text-slate-600"} />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <section className="rounded-2xl bg-white p-4 shadow-sm border border-slate-200">
          <h2 className="font-semibold mb-3 flex items-center gap-2"><Monitor size={18} className="text-turquoise-600" /> Séances du jour par état</h2>
          {t.seances_jour.total === 0 ? <p className="text-sm text-slate-500">Aucune séance prévue aujourd'hui.</p> : (
            <ul className="space-y-2">
              {Object.entries(t.seances_jour.par_statut).map(([s, n]) => (
                <li key={s} className="flex items-center gap-2 text-sm">
                  <span className={`h-3 w-3 rounded-full ${COULEURS[s]}`} />
                  <span className="flex-1">{LIBELLES[s] || s}</span>
                  <span className="font-semibold tabular-nums">{n}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rounded-2xl bg-white p-4 shadow-sm border border-slate-200">
          <h2 className="font-semibold mb-3">Séances réalisées sur 6 mois</h2>
          <div className="flex items-end gap-2 h-36">
            {t.seances_par_mois.map((m) => (
              <div key={m.mois} className="flex-1 flex flex-col items-center justify-end h-full">
                <span className="text-xs tabular-nums mb-1">{m.nombre}</span>
                <div className="w-full rounded-t-md bg-turquoise-500" style={{ height: `${(m.nombre / max) * 100}%`, minHeight: m.nombre ? 4 : 2 }} />
                <span className="text-[11px] text-slate-500 mt-1">{m.mois.slice(5)}/{m.mois.slice(2, 4)}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
      {suivi && (
        <div className="grid lg:grid-cols-2 gap-4 mt-4">
          <section className="rounded-2xl bg-white p-4 shadow-sm border border-rose-200">
            <h2 className="font-semibold mb-3 flex items-center gap-2 text-rose-800"><AlertTriangle size={18} /> Valeurs biologiques critiques ({suivi.critiques.length})</h2>
            {!suivi.critiques.length ? <p className="text-sm text-slate-500">Aucune valeur critique dans les derniers bilans.</p> : (
              <ul className="space-y-2 text-sm">{suivi.critiques.map((c) => <li key={c.id}><b>{c.nom} {c.prenom}</b> <span className="text-slate-500">({dateFr(c.date)})</span><div className="text-rose-700">{c.messages.join(" · ")}</div></li>)}</ul>
            )}
          </section>
          <section className="rounded-2xl bg-white p-4 shadow-sm border border-orange-200">
            <h2 className="font-semibold mb-3 flex items-center gap-2 text-orange-800"><FlaskConical size={18} /> Bilans en retard ({suivi.en_retard.length})</h2>
            {!suivi.en_retard.length ? <p className="text-sm text-slate-500">Tous les patients ont un bilan de moins de {suivi.jours_limite} jours.</p> : (
              <ul className="space-y-1 text-sm">{suivi.en_retard.map((p) => <li key={p.id}><b>{p.nom} {p.prenom}</b> <span className="text-slate-500">— {p.dernier_bilan ? "dernier bilan le " + dateFr(p.dernier_bilan) : "aucun bilan"}</span></li>)}</ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
