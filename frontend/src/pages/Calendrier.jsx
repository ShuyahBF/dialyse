// Calendrier d'activité du centre : mois interactif (séances par état, réservations en attente, occupation, maintenances) ; un clic sur un jour ouvre la grille
// postes × créneaux de ce jour, où l'on réserve une place libre, confirme ou refuse les réservations. Tout est filtré par le centre de travail (serveur).
import { CalendarDays, ChevronLeft, ChevronRight, Plus, RefreshCw, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import { Pastille } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import FormulaireReservation from "../composants/FormulaireReservation.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { aujourdhui } from "../lib/format.js";

const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
const JOURS_COURTS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const COULEUR_STATUT = { planifiee: "bleu", en_cours: "orange", terminee: "vert", absente: "rouge" };

const pad = (n) => String(n).padStart(2, "0");
const iso = (a, m, j) => `${a}-${pad(m + 1)}-${pad(j)}`;

/** Jour détaillé : grille postes × créneaux, réservations du jour. */
function JourDetail({ jour, onFermer, onChange }) {
  const { avecToast, toast, utilisateur } = useApp();
  const [d, setD] = useState(null);
  const [reserver, setReserver] = useState(null);       // { creneau, poste_id } d'une case libre
  const peutReserver = ["secretariat", "medecin", "infirmier", "admin", "super_admin"].includes(utilisateur.role);
  const charger = useCallback(() => api(`/calendrier/jour?date=${jour}`).then(setD), [jour]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const apres = async () => { setReserver(null); await charger(); onChange(); };
  const [a, m, j] = jour.split("-");
  return (
    <Modal large titre={`${j}/${m}/${a}`} onFermer={onFermer} pied={<><Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation du jour", charger, () => "Jour actualisé")}>Actualiser</Bouton><Bouton onClick={onFermer}>Fermer</Bouton></>}>
      {!d ? <div className="flex justify-center py-8"><span className="jauge" /></div> : (
        <>
          {d.maintenances.length > 0 && <p className="mb-2 flex items-center gap-2 rounded-lg bg-orange-50 p-2 text-sm text-orange-900"><Wrench size={16} /> Maintenance prévue : {d.maintenances.join(", ")}</p>}
          <div className="overflow-x-auto">
            <table className="tableau" data-sans-defilement>
              <thead><tr><th>Poste</th>{d.creneaux.map((c) => <th key={c}>{c} · {d.heures_creneaux[c]}</th>)}</tr></thead>
              <tbody>
                {d.postes.map((p) => (
                  <tr key={p.id}>
                    <td className="font-medium">{p.nom}{p.isolement && <span className="ml-1 text-xs text-violet-700">(isolement)</span>}{p.statut !== "actif" && <span className="ml-1 text-xs text-rose-700">({p.statut === "maintenance" ? "maintenance" : "hors service"})</span>}</td>
                    {d.creneaux.map((c) => {
                      const s = d.cellules.find((x) => x.poste_id === p.id && x.creneau === c)?.seance;
                      return (
                        <td key={c}>
                          {s ? <div><p className="font-medium text-emeraude">{s.patient.nom} {s.patient.prenom}</p>
                            <Pastille couleur={COULEUR_STATUT[s.statut] || "gris"}>{s.statut_libelle}</Pastille>
                            {s.confirmation_wa === "confirmee" && <span className="ml-1 text-xs text-emerald-700">✓ confirmé par WhatsApp</span>}
                            {s.confirmation_wa === "empeche" && <span className="ml-1 text-xs text-rose-700">empêché (WhatsApp)</span>}</div>
                            : p.statut === "actif" && peutReserver
                              ? <button type="button" onClick={() => setReserver({ creneau: c, poste_id: p.id })} className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold text-emeraude ring-1 ring-emeraude/30 hover:bg-emeraude/5"><Plus size={13} /> Libre · réserver</button>
                              : <span className="text-xs text-slate-400">{p.statut === "actif" ? "Libre" : "—"}</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {d.reservations.length > 0 && (
            <div className="mt-3">
              <h3 className="mb-1 text-sm font-semibold">Réservations du jour</h3>
              <ul className="space-y-1 text-sm">{d.reservations.map((r) => <li key={r.id} className="flex flex-wrap items-center gap-2">
                <Pastille couleur={r.statut === "confirmee" ? "vert" : "violet"}>{r.statut_libelle}</Pastille><span className="font-medium">{r.patient_nom}</span><span className="text-slate-500">{r.creneau} · {r.motif}</span></li>)}</ul>
            </div>
          )}
        </>
      )}
      {reserver && <FormulaireReservation date={jour} creneau={reserver.creneau} posteId={reserver.poste_id} onFermer={() => setReserver(null)} onFait={apres} />}
    </Modal>
  );
}

export default function Calendrier() {
  const { avecToast, toast, rafraichirCompteurs } = useApp();
  const auj = aujourdhui();
  const [vue, setVue] = useState({ a: Number(auj.slice(0, 4)), m: Number(auj.slice(5, 7)) - 1 });
  const [cal, setCal] = useState(null);
  const [jour, setJour] = useState(null);
  const debut = iso(vue.a, vue.m, 1), fin = iso(vue.a, vue.m, new Date(vue.a, vue.m + 1, 0).getDate());
  const charger = useCallback(async () => { const c = await api(`/calendrier?du=${debut}&au=${fin}`); setCal(c); return c; }, [debut, fin]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const parDate = useMemo(() => Object.fromEntries((cal?.jours || []).map((j) => [j.date, j])), [cal]);
  const decalage = (new Date(vue.a, vue.m, 1).getDay() + 6) % 7;                 // lundi = 0
  const cases = [...Array(decalage).fill(null), ...Array(new Date(vue.a, vue.m + 1, 0).getDate()).fill(0).map((_, i) => i + 1)];
  const aller = (n) => setVue((v) => { const d = new Date(v.a, v.m + n, 1); return { a: d.getFullYear(), m: d.getMonth() }; });
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><CalendarDays size={24} className="text-citron" /> Calendrier D'Activité</h1>
        <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation du calendrier", charger, (c) => `Calendrier actualisé (${c.jours.length} jours)`)}>Actualiser</Bouton>
      </div>
      <BandeauVersion className="mb-3" />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Bouton petit icone={ChevronLeft} onClick={() => aller(-1)}>Mois précédent</Bouton>
        <span className="min-w-[9rem] text-center text-lg font-semibold capitalize">{MOIS[vue.m]} {vue.a}</span>
        <Bouton petit icone={ChevronRight} onClick={() => aller(1)}>Mois suivant</Bouton>
        <Bouton petit variante="orange" onClick={() => setVue({ a: Number(auj.slice(0, 4)), m: Number(auj.slice(5, 7)) - 1 })}>Aujourd'hui</Bouton>
        <Bouton petit onClick={() => setJour(auj)}>Voir aujourd'hui en détail</Bouton>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-xs font-semibold text-ardoise">{JOURS_COURTS.map((j) => <div key={j}>{j}</div>)}</div>
      <div className="mt-1 grid grid-cols-7 gap-1" role="grid" aria-label="Calendrier du mois">
        {cases.map((n, i) => {
          if (!n) return <div key={"v" + i} />;
          const dt = iso(vue.a, vue.m, n), j = parDate[dt];
          const total = j ? j.planifiee + j.en_cours + j.terminee + j.absente : 0;
          return (
            <button key={dt} type="button" onClick={() => setJour(dt)} aria-label={`${n} ${MOIS[vue.m]} : ${total} séance(s)`}
              className={`min-h-[4.6rem] rounded-xl p-1.5 text-left ring-1 transition hover:ring-emeraude ${dt === auj ? "bg-orange-50 ring-citron" : "bg-white ring-encre/10"}`}>
              <div className="flex items-center justify-between"><span className={`text-sm font-semibold ${dt === auj ? "text-citron" : ""}`}>{n}</span>
                {j?.reservations_attente > 0 && <span className="rounded-full bg-violet-600 px-1.5 text-[10px] font-bold text-white" title="Réservations en attente">{j.reservations_attente}</span>}</div>
              {j && total > 0 && (
                <div className="mt-1 space-y-0.5 text-[10px] leading-tight">
                  <div className="flex flex-wrap gap-x-1.5">
                    {j.planifiee > 0 && <span className="text-sky-700">{j.planifiee} prévue(s)</span>}
                    {j.en_cours > 0 && <span className="text-orange-700">{j.en_cours} en cours</span>}
                    {j.terminee > 0 && <span className="text-emerald-700">{j.terminee} faite(s)</span>}
                    {j.absente > 0 && <span className="text-rose-700">{j.absente} absent(s)</span>}
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-200" title={`Occupation ${j.occupation_pct} %`}><div className={`h-full ${j.occupation_pct >= 90 ? "bg-rose-500" : j.occupation_pct >= 60 ? "bg-orange-400" : "bg-emerald-500"}`} style={{ width: `${Math.min(100, j.occupation_pct)}%` }} /></div>
                </div>
              )}
              {j?.maintenances?.length > 0 && <Wrench size={12} className="mt-0.5 text-orange-600" aria-label="Maintenance prévue" />}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-slate-500">Cliquez sur un jour pour voir la grille des postes et réserver une place. Pastille violette : réservations à traiter. Barre : taux d'occupation (vert &lt; 60 %, orange &lt; 90 %, rouge ≥ 90 %).</p>
      {jour && <JourDetail jour={jour} onFermer={() => setJour(null)} onChange={() => { charger().catch(() => {}); rafraichirCompteurs?.(); }} />}
    </div>
  );
}
