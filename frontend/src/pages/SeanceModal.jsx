// Fiche d'une séance (fenêtre modale) : étapes planifiée → démarrer → surveiller / incidents → terminer → valider.
// Le secrétariat ne voit que l'organisation (déplacer, annuler) : le serveur ne lui envoie aucune constante.
import { AlertTriangle, CalendarClock, CheckCircle2, Flag, HeartPulse, Play, Plus, Siren, UserX, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import Bouton from "../composants/Bouton.jsx";
import { Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateFr, dateHeureFr, nb } from "../lib/format.js";
import { COULEUR_SEANCE } from "./Planning.jsx";

const SOIGNANTS = ["medecin", "infirmier", "admin", "super_admin"];
const vide = (o) => Object.values(o).every((v) => v === "" || v === undefined);

/** Tension « sys/dia » ; seulement la systolique si la diastolique n'est pas saisie. */
const tension = (c) => (c.tension_dia != null ? `${nb(c.tension_sys, 0)}/${nb(c.tension_dia, 0)}` : nb(c.tension_sys, 0));

/** Ligne de constantes (poids, tension, pouls, température, UF, Kt/V, durée) : seules les valeurs saisies sont affichées. */
function Constantes({ titre, c }) {
  if (!c) return null;
  const items = [
    c.poids != null && <>Poids <b>{nb(c.poids)}</b> kg</>,
    c.tension_sys != null && <>TA <b>{tension(c)}</b> mmHg</>,
    c.pouls != null && <>Pouls <b>{nb(c.pouls, 0)}</b></>,
    c.temperature != null && <>T° <b>{nb(c.temperature)}</b> °C</>,
    c.volume_uf_l != null && <>UF <b>{nb(c.volume_uf_l)}</b> l</>,
    c.kt_v != null && <>Kt/V <b>{nb(c.kt_v, 2)}</b></>,
    c.duree_reelle_min != null && <>durée <b>{nb(c.duree_reelle_min, 0)}</b> min</>,
  ].filter(Boolean);
  return (
    <div className="rounded-lg bg-slate-50 p-2.5 text-sm mb-2">
      <div className="font-medium mb-0.5">{titre}</div>
      <div className="tabular-nums text-slate-700">
        {items.map((it, i) => <span key={i}>{i > 0 && " · "}{it}</span>)}
        {c.symptomes && <div>Symptômes : {c.symptomes}</div>}
      </div>
    </div>
  );
}

function ChampsConstantes({ v, maj, poids = true }) {
  return (
    <div className="grid grid-cols-2 gap-x-2">
      {poids && <Texte libelle="Poids (kg)" type="number" step="0.1" valeur={v.poids} onChange={(x) => maj("poids", x)} />}
      <Texte libelle="Pouls" type="number" valeur={v.pouls} onChange={(x) => maj("pouls", x)} />
      <Texte libelle="Tension systolique" type="number" valeur={v.tension_sys} onChange={(x) => maj("tension_sys", x)} />
      <Texte libelle="Tension diastolique" type="number" valeur={v.tension_dia} onChange={(x) => maj("tension_dia", x)} />
      <Texte libelle="Température (°C)" type="number" step="0.1" valeur={v.temperature} onChange={(x) => maj("temperature", x)} />
    </div>
  );
}

export default function SeanceModal({ id, onFermer, onChange }) {
  const { utilisateur, avecToast, toast } = useApp();
  const soignant = SOIGNANTS.includes(utilisateur.role);
  const medecin = ["medecin", "admin", "super_admin"].includes(utilisateur.role);
  const [s, setS] = useState(null);
  const [acces, setAcces] = useState([]);
  const [pre, setPre] = useState({ poids: "", tension_sys: "", tension_dia: "", pouls: "", temperature: "", symptomes: "", acces_id: "", uf_prevue_l: "" });
  const [rel, setRel] = useState({ heure: "", tension_sys: "", tension_dia: "", pouls: "", pression_veineuse: "", uf_cumule_l: "", remarque: "" });
  const [inc, setInc] = useState({ type: "", description: "", conduite: "" });
  const [post, setPost] = useState({ poids: "", tension_sys: "", tension_dia: "", pouls: "", temperature: "", volume_uf_l: "", kt_v: "", duree_reelle_min: "", observations: "" });
  const [motif, setMotif] = useState("");
  const [depl, setDepl] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const fermerRef = useRef(onFermer); fermerRef.current = onFermer;

  const charger = useCallback(async () => {
    const x = await api(`/seances/${id}`);
    setS(x);
    return x;
  }, [id]);
  useEffect(() => {
    charger().then(async (x) => {
      if (soignant && x.statut === "planifiee") { try { setAcces(((await api(`/patients/${x.patient_id}`)).acces_vasculaires || []).filter((a) => a.actif)); } catch { /* pas d'accès listé */ } }
    }).catch((e) => { toast(e.message, "erreur"); fermerRef.current(); });
    if (soignant) api("/seances/listes").then((l) => setIncidents(l.incidents)).catch(() => {});
  }, [charger, toast, soignant]);

  /** Appelle une étape du cycle, recharge la fiche et le planning. Les nombres vides ne sont pas envoyés. */
  async function agir(libelle, chemin, corps, ok) {
    const x = await avecToast(libelle, () => api(`/seances/${id}/${chemin}`, { methode: "POST", corps }), () => ok);
    setS(x); onChange();
  }
  const nettoyer = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== ""));

  if (!s) return <Modal titre="Séance" large onFermer={onFermer}><div className="py-8 flex justify-center"><span className="jauge" /></div></Modal>;
  const critiques = (s.alertes || []).filter((a) => a.niveau === "critique");
  const attentions = (s.alertes || []).filter((a) => a.niveau !== "critique");
  return (
    <Modal titre={`${s.patient.nom} ${s.patient.prenom}`} large onFermer={onFermer} pied={<Bouton onClick={onFermer}>Fermer</Bouton>}>
      <div className="flex flex-wrap items-center gap-2 mb-3 text-sm">
        <Pastille couleur={COULEUR_SEANCE[s.statut]}>{s.statut_libelle}</Pastille>
        <span>{s.patient.code} · {dateFr(s.date)} · {s.creneau} · {s.poste_nom}</span>
        {s.serologie_positive && <Pastille couleur="rouge" icone={AlertTriangle}>Sérologie positive</Pastille>}
        {s.poste_isolement && <Pastille couleur="violet">Poste d'isolement</Pastille>}
        {s.validee_par && <Pastille couleur="vert" icone={CheckCircle2}>Validée par {s.validee_par}</Pastille>}
      </div>
      {critiques.map((a, i) => <p key={i} className="mb-1.5 flex items-center gap-2 rounded-lg bg-rose-100 text-rose-900 px-3 py-2 text-sm"><Siren size={16} /> {a.message}</p>)}
      {attentions.map((a, i) => <p key={i} className="mb-1.5 flex items-center gap-2 rounded-lg bg-orange-100 text-orange-900 px-3 py-2 text-sm"><AlertTriangle size={16} /> {a.message}</p>)}

      {soignant && s.pre && <Constantes titre="Début de séance" c={s.pre} />}
      {soignant && s.parametres && (
        <p className="text-sm text-slate-600 mb-2">Machine : {s.parametres.dialyseur || "—"} · débit sang {nb(s.parametres.debit_sang, 0) || "—"} · durée prévue {nb(s.parametres.duree_prevue_min, 0) || "—"} min{s.parametres.uf_prevue_l != null ? ` · UF prévue ${nb(s.parametres.uf_prevue_l)} l` : ""}</p>
      )}
      {soignant && (s.surveillance || []).length > 0 && (
        <div className="mb-3 overflow-x-auto"><table className="tableau"><thead><tr><th>Heure</th><th className="num">TA</th><th className="num">Pouls</th><th className="num">P. veineuse</th><th className="num">UF (l)</th><th>Remarque</th></tr></thead>
          <tbody>{s.surveillance.map((m) => <tr key={m.id}><td>{m.heure}</td><td className="num">{m.tension_sys != null ? tension(m) : ""}</td><td className="num">{nb(m.pouls, 0)}</td><td className="num">{nb(m.pression_veineuse, 0)}</td><td className="num">{nb(m.uf_cumule_l)}</td><td>{m.remarque}</td></tr>)}</tbody></table></div>
      )}
      {soignant && (s.incidents || []).length > 0 && (
        <ul className="mb-3 space-y-1.5">{s.incidents.map((i) => <li key={i.id} className="rounded-lg border border-orange-200 bg-orange-50 px-3 py-1.5 text-sm"><b>{i.heure} — {i.type}</b>{i.description && ` : ${i.description}`}{i.conduite && <div className="text-slate-600">Conduite : {i.conduite}</div>}</li>)}</ul>
      )}
      {soignant && (s.consommables || []).length > 0 && (
        <p className="text-sm text-slate-600 mb-2">Consommables : {s.consommables.map((c) => `${c.nom} × ${nb(c.quantite)} (lot ${c.lots.map((l) => l.numero).join(", ")})`).join(" · ")}</p>
      )}
      {soignant && (s.manques || []).length > 0 && (
        <p className="mb-1.5 flex items-center gap-2 rounded-lg bg-orange-100 text-orange-900 px-3 py-2 text-sm"><AlertTriangle size={16} /> Stock insuffisant, non décompté : {s.manques.join(", ")}</p>
      )}
      {soignant && s.post && <Constantes titre="Fin de séance" c={s.post} />}
      {soignant && s.observations && <p className="text-sm mb-2">Observations : {s.observations}</p>}
      {s.avis_medecin && <p className="text-sm mb-2">Avis du médecin : {s.avis_medecin}</p>}
      {s.motif && <p className="text-sm mb-2">Motif : {s.motif}</p>}
      {s.debut_a && <p className="text-xs text-slate-500">Début {dateHeureFr(s.debut_a)}{s.fin_a && ` · fin ${dateHeureFr(s.fin_a)}`}</p>}

      {/* ---- Planifiée : démarrer, déplacer, annuler ---- */}
      {s.statut === "planifiee" && (
        <div className="space-y-4 mt-3">
          {soignant && (
            <section className="rounded-xl border border-emerald-200 p-3">
              <h3 className="font-semibold mb-2 flex items-center gap-2 text-emerald-800"><Play size={16} /> Démarrer la séance</h3>
              <ChampsConstantes v={pre} maj={(k, x) => setPre({ ...pre, [k]: x })} />
              <Texte libelle="Symptômes" valeur={pre.symptomes} onChange={(x) => setPre({ ...pre, symptomes: x })} />
              <Liste libelle="Accès vasculaire utilisé" valeur={pre.acces_id} onChange={(x) => setPre({ ...pre, acces_id: x })} options={acces.map((a) => ({ valeur: a.id, libelle: `${a.type} — ${a.localisation}` }))} />
              <Texte libelle="Ultrafiltration prévue (l)" type="number" step="0.1" valeur={pre.uf_prevue_l} onChange={(x) => setPre({ ...pre, uf_prevue_l: x })} />
              <p className="text-xs text-slate-500 mb-2">Dialyseur, débits, durée et héparine reprennent la prescription du patient.</p>
              <Bouton icone={Play} variante="vert" disabled={!pre.poids || !pre.tension_sys || !pre.tension_dia}
                onClick={() => agir("Démarrage de la séance", "demarrer", { pre: nettoyer({ poids: pre.poids, tension_sys: pre.tension_sys, tension_dia: pre.tension_dia, pouls: pre.pouls, temperature: pre.temperature, symptomes: pre.symptomes }),
                  parametres: nettoyer({ acces_id: pre.acces_id, uf_prevue_l: pre.uf_prevue_l }) }, "Séance démarrée")}>Démarrer</Bouton>
            </section>
          )}
          <section className="rounded-xl border border-sky-200 p-3">
            <h3 className="font-semibold mb-2 flex items-center gap-2 text-sky-800"><CalendarClock size={16} /> Déplacer</h3>
            <div className="grid grid-cols-2 gap-x-2">
              <Texte libelle="Date" type="date" valeur={depl?.date ?? s.date} onChange={(x) => setDepl({ ...(depl || {}), date: x })} />
              <Liste libelle="Créneau" valeur={depl?.creneau ?? s.creneau} onChange={(x) => setDepl({ ...(depl || {}), creneau: x })} options={["matin", "midi", "soir"]} />
            </div>
            <Bouton icone={CalendarClock} variante="principal" disabled={!depl}
              onClick={async () => { const x = await avecToast("Déplacement", () => api(`/seances/${id}`, { methode: "PUT", corps: depl }), () => "Séance déplacée"); (x.alertes_planification || []).forEach((a) => toast("⚠ " + a, "erreur")); setS(x); setDepl(null); onChange(); }}>Déplacer</Bouton>
          </section>
          <section className="rounded-xl border border-rose-200 p-3">
            <h3 className="font-semibold mb-2 flex items-center gap-2 text-rose-800"><XCircle size={16} /> Annuler ou patient absent</h3>
            <Texte libelle="Motif (obligatoire pour une annulation)" valeur={motif} onChange={setMotif} />
            <div className="flex flex-wrap gap-2">
              <Bouton icone={XCircle} variante="rouge" disabled={!motif} onClick={() => agir("Annulation", "annuler", { motif }, "Séance annulée")}>Annuler la séance</Bouton>
              <Bouton icone={UserX} variante="orange" onClick={() => agir("Enregistrement de l'absence", "annuler", { absent: true, motif }, "Absence enregistrée")}>Patient absent</Bouton>
            </div>
          </section>
        </div>
      )}

      {/* ---- En cours : surveillance, incident, terminer ---- */}
      {s.statut === "en_cours" && soignant && (
        <div className="space-y-4 mt-3">
          <section className="rounded-xl border border-sky-200 p-3">
            <h3 className="font-semibold mb-2 flex items-center gap-2 text-sky-800"><HeartPulse size={16} /> Relevé de surveillance</h3>
            <div className="grid grid-cols-2 gap-x-2">
              <Texte libelle="Heure" type="time" valeur={rel.heure} onChange={(x) => setRel({ ...rel, heure: x })} />
              <Texte libelle="Pouls" type="number" valeur={rel.pouls} onChange={(x) => setRel({ ...rel, pouls: x })} />
              <Texte libelle="Tension systolique" type="number" valeur={rel.tension_sys} onChange={(x) => setRel({ ...rel, tension_sys: x })} />
              <Texte libelle="Tension diastolique" type="number" valeur={rel.tension_dia} onChange={(x) => setRel({ ...rel, tension_dia: x })} />
              <Texte libelle="Pression veineuse" type="number" valeur={rel.pression_veineuse} onChange={(x) => setRel({ ...rel, pression_veineuse: x })} />
              <Texte libelle="UF cumulée (l)" type="number" step="0.1" valeur={rel.uf_cumule_l} onChange={(x) => setRel({ ...rel, uf_cumule_l: x })} />
            </div>
            <Texte libelle="Remarque" valeur={rel.remarque} onChange={(x) => setRel({ ...rel, remarque: x })} />
            <Bouton icone={Plus} variante="principal" disabled={vide({ a: rel.tension_sys, b: rel.pouls, c: rel.pression_veineuse })}
              onClick={async () => { await agir("Ajout du relevé", "surveillance", nettoyer(rel), "Relevé ajouté"); setRel({ heure: "", tension_sys: "", tension_dia: "", pouls: "", pression_veineuse: "", uf_cumule_l: "", remarque: "" }); }}>Ajouter le relevé</Bouton>
          </section>
          <section className="rounded-xl border border-orange-200 p-3">
            <h3 className="font-semibold mb-2 flex items-center gap-2 text-orange-800"><Siren size={16} /> Déclarer un incident</h3>
            <Liste libelle="Type d'incident" valeur={inc.type} onChange={(x) => setInc({ ...inc, type: x })} options={incidents} />
            <Texte libelle="Description" valeur={inc.description} onChange={(x) => setInc({ ...inc, description: x })} />
            <Texte libelle="Conduite tenue" valeur={inc.conduite} onChange={(x) => setInc({ ...inc, conduite: x })} />
            <Bouton icone={Siren} variante="orange" disabled={!inc.type} onClick={async () => { await agir("Déclaration de l'incident", "incident", inc, "Incident déclaré"); setInc({ type: "", description: "", conduite: "" }); }}>Déclarer l'incident</Bouton>
          </section>
          <section className="rounded-xl border border-emerald-200 p-3">
            <h3 className="font-semibold mb-2 flex items-center gap-2 text-emerald-800"><Flag size={16} /> Terminer la séance</h3>
            <ChampsConstantes v={post} maj={(k, x) => setPost({ ...post, [k]: x })} />
            <div className="grid grid-cols-3 gap-x-2">
              <Texte libelle="UF réalisée (l)" type="number" step="0.1" valeur={post.volume_uf_l} onChange={(x) => setPost({ ...post, volume_uf_l: x })} />
              <Texte libelle="Kt/V" type="number" step="0.01" valeur={post.kt_v} onChange={(x) => setPost({ ...post, kt_v: x })} />
              <Texte libelle="Durée (min)" type="number" valeur={post.duree_reelle_min} onChange={(x) => setPost({ ...post, duree_reelle_min: x })} />
            </div>
            <Texte libelle="Observations" valeur={post.observations} onChange={(x) => setPost({ ...post, observations: x })} />
            <Bouton icone={Flag} variante="vert" disabled={!post.poids}
              onClick={() => agir("Clôture de la séance", "terminer", { observations: post.observations, post: nettoyer({ poids: post.poids, tension_sys: post.tension_sys, tension_dia: post.tension_dia, pouls: post.pouls,
                temperature: post.temperature, volume_uf_l: post.volume_uf_l, kt_v: post.kt_v, duree_reelle_min: post.duree_reelle_min }) }, "Séance terminée")}>Terminer la séance</Bouton>
          </section>
        </div>
      )}

      {/* ---- Terminée : validation par le médecin ---- */}
      {s.statut === "terminee" && !s.validee_par && medecin && (
        <section className="rounded-xl border border-emerald-200 p-3 mt-3">
          <h3 className="font-semibold mb-2 flex items-center gap-2 text-emerald-800"><CheckCircle2 size={16} /> Validation médicale</h3>
          <Texte libelle="Avis du médecin" valeur={motif} onChange={setMotif} />
          <p className="text-xs text-slate-500 mb-2">Une séance validée est verrouillée.</p>
          <Bouton icone={CheckCircle2} variante="vert" onClick={() => agir("Validation", "valider", { avis: motif }, "Séance validée et verrouillée")}>Valider la séance</Bouton>
        </section>
      )}
    </Modal>
  );
}
