// « Aujourd'hui » : l'état des dialyses EN DIRECT, poste par poste. Relu automatiquement toutes les 30 secondes ; « Actualiser » force la relecture (toast en cours puis résultat).
// Les alertes cliniques n'arrivent que pour le personnel médical (le serveur ne les envoie pas au secrétariat).
import { Activity, AlertTriangle, CheckCircle2, Clock, MessageCircle, RefreshCw, UserX, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import { Pastille } from "../composants/Champs.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateFr } from "../lib/format.js";

/** « 135 » → « 2 h 15 » */
const duree = (min) => (min >= 60 ? `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")}` : `${min} min`);

const ETAT = {
  libre: ["Libre", "border-emerald-300 bg-emerald-50", "vert"],
  occupe: ["En dialyse", "border-sky-400 bg-sky-50", "bleu"],
  maintenance: ["En maintenance", "border-orange-300 bg-orange-50", "orange"],
  hors_service: ["Hors service", "border-slate-300 bg-slate-100", "gris"],
};

function Chiffre({ icone: Icone, valeur, libelle, couleur = "text-encre", lien }) {
  const contenu = (
    <div className="flex items-center gap-3 rounded-2xl bg-white p-3 ring-1 ring-encre/5">
      <Icone size={22} className={couleur} aria-hidden="true" />
      <div><p className={`text-2xl font-bold tabular-nums leading-none ${couleur}`}>{valeur}</p><p className="mt-1 text-xs text-ardoise">{libelle}</p></div>
    </div>
  );
  return lien ? <Link to={lien} className="block hover:opacity-90">{contenu}</Link> : contenu;
}

function CartePoste({ p }) {
  const [libelle, classe, couleur] = ETAT[p.etat];
  const c = p.en_cours;
  return (
    <div className={`rounded-2xl border-2 p-3 ${classe}`} data-testid={`poste-${p.nom}`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="font-semibold">{p.nom}{p.isolement && <span className="ml-1 text-xs font-medium text-violet-700">(isolement)</span>}</h3>
        <Pastille couleur={couleur}>{libelle}</Pastille>
      </div>
      {c ? (
        <div>
          <p className="font-semibold text-emeraude">{c.patient.nom} {c.patient.prenom} <span className="text-xs font-normal text-slate-500">{c.patient.code}</span></p>
          <div className="my-1.5 h-2.5 overflow-hidden rounded-full bg-white/80 ring-1 ring-encre/10" role="progressbar" aria-valuenow={c.progression_pct} aria-valuemin={0} aria-valuemax={100} aria-label="Progression de la séance">
            <div className={`h-full ${c.depasse ? "bg-rose-500" : c.restant_min <= 30 ? "bg-orange-400" : "bg-sky-500"}`} style={{ width: `${c.progression_pct}%` }} />
          </div>
          <p className="text-xs text-slate-600">{c.debut} → {c.fin_prevue} · <b>{c.depasse ? "durée prévue dépassée" : `reste ${duree(c.restant_min)}`}</b> ({c.progression_pct} %)</p>
          {c.alertes?.map((a, i) => <p key={i} className={`mt-1 flex items-start gap-1 text-xs ${a.niveau === "critique" ? "font-semibold text-rose-700" : "text-orange-700"}`}><AlertTriangle size={13} className="mt-0.5 shrink-0" />{a.message}</p>)}
          {c.serologie_positive && <Pastille couleur="rouge">Sérologie positive</Pastille>}
        </div>
      ) : p.etat === "libre" ? <p className="text-sm text-emerald-800">Disponible{p.prochaine ? "" : " : aucune séance prévue"}</p>
        : <p className="text-sm text-slate-600">{p.maintenance_du_jour ? "Maintenance prévue aujourd'hui" : "Indisponible"}</p>}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-1 border-t border-encre/10 pt-1.5 text-xs text-slate-600">
        <span>{p.prochaine ? <>Prochain : <b>{p.prochaine.heure}</b> · {p.prochaine.patient.nom} {p.prochaine.patient.prenom}</> : "Pas d'autre séance prévue"}</span>
        <span className="inline-flex items-center gap-1"><CheckCircle2 size={12} className="text-emerald-600" /> {p.terminees} terminée(s)</span>
      </div>
    </div>
  );
}

export default function Aujourdhui() {
  const { avecToast, toast, rafraichirCompteurs } = useApp();
  const [d, setD] = useState(null);
  const charger = useCallback(async () => { const r = await api("/aujourdhui"); setD(r); rafraichirCompteurs?.(); return r; }, [rafraichirCompteurs]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); const t = setInterval(() => charger().catch(() => {}), 30000); return () => clearInterval(t); }, [charger, toast]);
  if (!d) return <div className="flex justify-center py-10"><span className="jauge" /></div>;
  const alertes = d.en_retard.length + d.depassees.length + d.empeches.length + d.fin_proche.length;
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><Activity size={24} className="text-citron" /> Aujourd'hui <span className="text-base font-medium text-ardoise">· {dateFr(d.date)} · {d.heure}</span></h1>
        <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation de la journée", charger, (r) => `Journée actualisée : ${r.comptes.en_cours} en cours, ${r.comptes.terminee} terminée(s)`)}>Actualiser</Bouton>
      </div>
      <BandeauVersion className="mb-1" />
      <p className="mb-3 text-xs text-slate-500">Relu automatiquement toutes les 30 secondes. Heure du serveur : {d.heure}.</p>

      {/* Alertes du moment : EN HAUT de la page (règle du propriétaire) */}
      {alertes > 0 && (
        <div className="mb-4 space-y-2" data-testid="alertes-du-jour">
          {d.en_retard.length > 0 && <div className="rounded-xl bg-rose-50 p-3 text-sm ring-1 ring-rose-200"><p className="mb-1 flex items-center gap-2 font-semibold text-rose-800"><Clock size={16} /> {d.en_retard.length} séance(s) en retard à démarrer</p>
            <ul className="space-y-0.5">{d.en_retard.map((c) => <li key={c.id}>{c.heure} · <b>{c.patient.nom} {c.patient.prenom}</b> — {duree(c.retard_min)} de retard</li>)}</ul></div>}
          {d.depassees.length > 0 && <div className="rounded-xl bg-rose-50 p-3 text-sm ring-1 ring-rose-200"><p className="flex items-center gap-2 font-semibold text-rose-800"><AlertTriangle size={16} /> Durée prévue dépassée : {d.depassees.map((c) => `${c.patient.nom} ${c.patient.prenom}`).join(", ")}</p></div>}
          {d.fin_proche.length > 0 && <div className="rounded-xl bg-orange-50 p-3 text-sm ring-1 ring-orange-200"><p className="mb-1 flex items-center gap-2 font-semibold text-orange-800"><Clock size={16} /> Se terminent bientôt</p>
            <ul>{d.fin_proche.map((c) => <li key={c.id}>{c.patient.nom} {c.patient.prenom} — reste {duree(c.restant_min)} (fin prévue {c.fin_prevue})</li>)}</ul></div>}
          {d.empeches.length > 0 && <div className="rounded-xl bg-orange-50 p-3 text-sm ring-1 ring-orange-200"><p className="flex items-center gap-2 font-semibold text-orange-800"><UserX size={16} /> Patient(s) empêché(s) (réponse WhatsApp) : {d.empeches.map((c) => `${c.patient.nom} ${c.patient.prenom}`).join(", ")}</p></div>}
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Chiffre icone={Activity} valeur={d.comptes.en_cours} libelle="En dialyse maintenant" couleur="text-sky-700" />
        <Chiffre icone={CheckCircle2} valeur={d.comptes.terminee} libelle="Terminées" couleur="text-emerald-700" />
        <Chiffre icone={Clock} valeur={d.comptes.planifiee} libelle={`À venir (sur ${d.total_prevu} prévues)`} couleur="text-ardoise" />
        <Chiffre icone={UserX} valeur={d.comptes.absente} libelle="Absents" couleur="text-rose-700" />
        <Chiffre icone={Wrench} valeur={`${d.postes_occupes}/${d.postes_occupes + d.postes_libres}`} libelle={`Postes occupés${d.postes_indisponibles ? ` · ${d.postes_indisponibles} indisponible(s)` : ""}`} couleur="text-encre" />
        <Chiffre icone={MessageCircle} valeur={d.reservations_attente + d.demandes_wa} libelle="Réservations à traiter" couleur="text-violet-700" lien="/reservations" />
      </div>
      {d.a_valider != null && d.a_valider > 0 && <p className="mb-3 rounded-lg bg-sky-50 p-2 text-sm text-sky-900">{d.a_valider} séance(s) terminée(s) à valider par le médecin.</p>}

      <h2 className="mb-2 text-lg font-semibold">Les postes</h2>
      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{d.postes.length === 0 ? <p className="text-sm text-slate-500">Aucun poste : ajoutez-les dans « Postes De Dialyse ».</p> : d.postes.map((p) => <CartePoste key={p.id} p={p} />)}</div>

      <h2 className="mb-2 text-lg font-semibold">Séances à venir aujourd'hui</h2>
      <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
        <table className="tableau" data-sans-defilement>
          <thead><tr><th>Heure</th><th>Patient</th><th>Créneau</th><th>État</th></tr></thead>
          <tbody>
            {d.a_venir.length === 0 && <tr><td colSpan={4} className="py-5 text-center text-slate-500">Aucune autre séance à venir aujourd'hui.</td></tr>}
            {d.a_venir.map((c) => (
              <tr key={c.id}><td className="tabular-nums font-semibold text-emeraude">{c.heure}</td><td>{c.patient.nom} {c.patient.prenom} <span className="text-xs text-slate-500">{c.patient.code}</span></td><td>{c.creneau}</td>
                <td>{c.confirmation_wa === "confirmee" ? <Pastille couleur="vert" icone={MessageCircle}>Confirmé par WhatsApp</Pastille> : <Pastille couleur="bleu">Planifiée</Pastille>}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
