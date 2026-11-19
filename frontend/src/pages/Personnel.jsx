// Planning du personnel : grille semaine (créneaux × jours), couverture des séances (soignants requis, médecin), absences ; équipe du centre.
import { ChevronLeft, ChevronRight, Copy, Pencil, Plus, RefreshCw, Save, Users, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { ajouterJours, aujourdhui, dateFr, fcfa } from "../lib/format.js";

const JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const CRENEAUX = ["matin", "midi", "soir"];
const TYPES = [{ valeur: "present", libelle: "Présent" }, { valeur: "conge", libelle: "Congé" }, { valeur: "maladie", libelle: "Maladie" }, { valeur: "formation", libelle: "Formation" }];
const lundiDe = (iso) => { const d = new Date(iso + "T12:00:00"); return ajouterJours(iso, -((d.getDay() + 6) % 7)); };
const court = (f) => ({ "Néphrologue": "Néph.", "Infirmier(ère)": "Inf.", "Aide-soignant(e)": "AS", "Technicien biomédical": "Tech.", "Secrétaire": "Secr.", "Agent d'entretien": "Entr." }[f] || f);

function Onglets({ actif, onChoix }) {
  return <div className="mb-3 flex gap-1 border-b border-slate-200">{[["planning", "Planning"], ["equipe", "Équipe"]].map(([k, l]) => (
    <button key={k} type="button" onClick={() => onChoix(k)} className={`border-b-2 px-3 py-2 text-sm font-semibold ${actif === k ? "border-citron text-encre" : "border-transparent text-slate-500 hover:text-encre"}`}>{l}</button>))}</div>;
}

export default function Personnel() {
  const { avecToast, toast, utilisateur, rafraichirCompteurs } = useApp();
  const peutGerer = ["admin", "super_admin", "medecin"].includes(utilisateur.role);
  const [onglet, setOnglet] = useState("planning");
  const [lundi, setLundi] = useState(lundiDe(aujourdhui()));
  const [plan, setPlan] = useState(null);
  const [equipe, setEquipe] = useState([]);
  const [modal, setModal] = useState(null);
  const [form, setForm] = useState({});
  const charger = useCallback(async () => {
    const [p, e] = await Promise.all([api(`/personnel/planning?du=${lundi}&au=${ajouterJours(lundi, 6)}`), api("/personnel?actifs=false")]);
    setPlan(p); setEquipe(e); rafraichirCompteurs?.();
    return p;
  }, [lundi, rafraichirCompteurs]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const agir = async (enCours, action, ok) => { await avecToast(enCours, action, ok); setModal(null); await charger(); };
  const jours = [...Array(7)].map((_, i) => ajouterJours(lundi, i));
  const actifs = equipe.filter((p) => p.actif);
  const dans = (jour, c) => (plan?.affectations || []).filter((a) => a.date === jour && (a.creneau === c || a.creneau === "journee"));
  const couv = (jour, c) => plan?.couverture.find((x) => x.date === jour && x.creneau === c);
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><Users size={24} className="text-citron" /> Planning Du Personnel</h1>
        <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation du planning", charger, (p) => `${p.affectations.length} affectation(s) sur la semaine`)}>Actualiser</Bouton>
      </div>
      <BandeauVersion className="mb-3" />
      <Onglets actif={onglet} onChoix={setOnglet} />

      {onglet === "planning" && plan && (
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Bouton petit icone={ChevronLeft} onClick={() => setLundi(ajouterJours(lundi, -7))}>Semaine précédente</Bouton>
            <span className="min-w-[10rem] text-center font-semibold">Semaine du {dateFr(lundi)}</span>
            <Bouton petit icone={ChevronRight} onClick={() => setLundi(ajouterJours(lundi, 7))}>Semaine suivante</Bouton>
            <Bouton petit variante="orange" onClick={() => setLundi(lundiDe(aujourdhui()))}>Cette semaine</Bouton>
            {peutGerer && <Bouton petit icone={Copy} onClick={() => agir("Copie du planning", () => api("/personnel/planning/dupliquer", { methode: "POST", corps: { du: lundi, vers: ajouterJours(lundi, 7) } }), (r) => `${r.copiees} affectation(s) copiée(s) vers la semaine suivante, ${r.ignorees} ignorée(s)`)}>Copier vers la semaine suivante</Bouton>}
          </div>
          <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
            <table className="tableau" data-sans-defilement>
              <thead><tr><th>Créneau</th>{jours.map((j, i) => <th key={j} className={j === aujourdhui() ? "text-citron" : ""}>{JOURS[i]} {j.slice(8)}/{j.slice(5, 7)}</th>)}</tr></thead>
              <tbody>
                {CRENEAUX.map((c) => (
                  <tr key={c}>
                    <td className="font-semibold capitalize">{c}</td>
                    {jours.map((j) => {
                      const k = couv(j, c);
                      const alerte = k && (k.manque_soignants > 0 || k.sans_medecin);
                      return (
                        <td key={j} className={`align-top ${alerte ? "bg-rose-50" : ""}`}>
                          {k?.seances > 0 && <p className={`mb-1 text-[11px] font-semibold ${alerte ? "text-rose-700" : "text-emerald-700"}`}>{k.seances} séance(s) · soignants {k.soignants}/{k.soignants_requis}{k.sans_medecin ? " · sans médecin" : ""}</p>}
                          <div className="flex flex-wrap gap-1">
                            {dans(j, c).map((a) => (
                              <span key={a.id} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${a.type === "present" ? "bg-sky-100 text-sky-900" : "bg-slate-200 text-slate-700"}`} title={`${a.personnel_nom} — ${a.fonction}${a.type !== "present" ? " (" + a.type + ")" : ""}`}>
                                {a.personnel_nom.split(" ")[0]} <span className="opacity-60">{court(a.fonction)}</span>{a.type !== "present" && <i>({a.type})</i>}
                                {peutGerer && <button type="button" aria-label={`Retirer ${a.personnel_nom}`} onClick={() => agir("Retrait", () => api(`/personnel/affectations/${a.id}`, { methode: "DELETE" }), () => "Affectation retirée")}><X size={11} /></button>}
                              </span>
                            ))}
                            {peutGerer && <button type="button" aria-label="Affecter" onClick={() => { setForm({ date: j, creneau: c, type: "present" }); setModal({ type: "affecter" }); }} className="rounded-full px-1.5 text-xs font-bold text-emeraude ring-1 ring-emeraude/30 hover:bg-emeraude/5"><Plus size={12} /></button>}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-slate-500">Règle : 1 soignant (infirmier ou aide-soignant) pour {plan.regle} patients, et un néphrologue à chaque créneau qui a des séances. Un créneau en rouge est sous-doté (alerte, aucun blocage).
            {["admin", "super_admin"].includes(utilisateur.role) && <button type="button" className="ml-2 font-semibold text-emeraude underline" onClick={() => { setForm({ n: plan.regle }); setModal({ type: "regle" }); }}>Changer la règle</button>}</p>
        </div>
      )}

      {onglet === "equipe" && (
        <div>
          {peutGerer && <div className="mb-2"><Bouton icone={Plus} variante="principal" onClick={() => { setForm({ fonction: "Infirmier(ère)" }); setModal({ type: "membre" }); }}>Nouveau membre</Bouton></div>}
          <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
            <table className="tableau"><thead><tr><th>Nom</th><th>Fonction</th><th>Téléphone</th>{equipe.some((p) => p.cout_mensuel !== undefined) && <th className="num">Coût mensuel</th>}<th>État</th>{peutGerer && <th>Actions</th>}</tr></thead>
              <tbody>{equipe.map((p) => (
                <tr key={p.id}><td className="font-medium text-emeraude">{p.nom}</td><td>{p.fonction}</td><td>{p.telephone || "—"}</td>
                  {equipe.some((x) => x.cout_mensuel !== undefined) && <td className="num tabular-nums">{p.cout_mensuel !== undefined ? fcfa(p.cout_mensuel) : "—"}</td>}
                  <td>{p.actif ? <Pastille couleur="vert">Actif</Pastille> : <Pastille>Inactif</Pastille>}</td>
                  {peutGerer && <td className="whitespace-nowrap"><BoutonIcone icone={Pencil} libelle="Modifier" onClick={() => { setForm({ nom: p.nom, fonction: p.fonction, telephone: p.telephone || "", cout_mensuel: p.cout_mensuel ?? "", actif: p.actif }); setModal({ type: "membre", p }); }} /></td>}</tr>))}</tbody>
              {equipe.some((p) => p.cout_mensuel !== undefined) && <tfoot><tr className="font-semibold"><td>Total · {equipe.filter((p) => p.actif).length} actif(s)</td><td /><td /><td className="num tabular-nums">{fcfa(equipe.filter((p) => p.actif).reduce((s, p) => s + (p.cout_mensuel || 0), 0))}</td><td />{peutGerer && <td />}</tr></tfoot>}
            </table>
          </div>
        </div>
      )}

      {modal?.type === "affecter" && (
        <Modal titre={`Affecter — ${dateFr(form.date)} · ${form.creneau}`} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={Save} variante="principal" disabled={!form.personnel_id} onClick={() => agir("Affectation", () => api("/personnel/affectations", { methode: "POST", corps: { ...form, creneau: form.type === "present" ? form.creneau : (form.type_journee ? "journee" : form.creneau) } }), () => "Affectation enregistrée")}>Enregistrer</Bouton></>}>
          <Liste libelle="Membre de l'équipe" valeur={form.personnel_id} onChange={(v) => setForm({ ...form, personnel_id: v })} options={actifs.map((p) => ({ valeur: p.id, libelle: `${p.nom} (${p.fonction})` }))} />
          <Liste libelle="Type" valeur={form.type} onChange={(v) => setForm({ ...form, type: v })} options={TYPES} vide={null} />
          {form.type !== "present" && <label className="mb-3 flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-emeraude" checked={!!form.type_journee} onChange={(e) => setForm({ ...form, type_journee: e.target.checked })} /> Toute la journée</label>}
        </Modal>
      )}
      {modal?.type === "membre" && (
        <Modal titre={modal.p ? "Modifier le membre" : "Nouveau membre"} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={Save} variante="principal" disabled={!form.nom} onClick={() => agir("Enregistrement", () => api(modal.p ? `/personnel/${modal.p.id}` : "/personnel", { methode: modal.p ? "PUT" : "POST", corps: form }), () => "Membre enregistré")}>Enregistrer</Bouton></>}>
          <Texte libelle="Nom" valeur={form.nom} onChange={(v) => setForm({ ...form, nom: v })} placeholder="ILBOUDO Awa" />
          <Liste libelle="Fonction" valeur={form.fonction} onChange={(v) => setForm({ ...form, fonction: v })} options={["Néphrologue", "Infirmier(ère)", "Aide-soignant(e)", "Technicien biomédical", "Secrétaire", "Agent d'entretien", "Autre"]} vide={null} />
          <Texte libelle="Téléphone" valeur={form.telephone} onChange={(v) => setForm({ ...form, telephone: v })} />
          {["admin", "super_admin", "direction"].includes(utilisateur.role) && <Texte libelle="Coût mensuel (FCFA)" type="number" valeur={form.cout_mensuel} onChange={(v) => setForm({ ...form, cout_mensuel: v })} aide="Salaire et charges : sert au calcul de rentabilité (visible de l'administration seulement)." />}
          {modal.p && <label className="mb-3 flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-emeraude" checked={!!form.actif} onChange={(e) => setForm({ ...form, actif: e.target.checked })} /> Membre actif</label>}
        </Modal>
      )}
      {modal?.type === "regle" && (
        <Modal titre="Règle de couverture" onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton icone={Save} variante="principal" onClick={() => agir("Enregistrement", () => api("/personnel/regles", { methode: "PUT", corps: { patients_par_infirmier: Number(form.n) } }), () => "Règle enregistrée")}>Enregistrer</Bouton></>}>
          <Texte libelle="Patients par infirmier (ou aide-soignant)" type="number" min={1} max={12} valeur={form.n} onChange={(v) => setForm({ n: v })} aide="Valeur usuelle : 4. À valider avec le médecin responsable." />
        </Modal>
      )}
    </div>
  );
}
