// Patients : liste triable avec recherche, création, et DOSSIER en fenêtre modale (règle 20) à onglets :
// Identité · Médical · Prescription · Accès vasculaires · Séances. Les onglets médicaux n'existent pas pour le secrétariat.
import { AlertTriangle, FolderOpen, Plus, RefreshCw, Save, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import Bilans from "../composants/Bilans.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Case, Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateFr, nb } from "../lib/format.js";
import { useFormulaire, useListes } from "../lib/listes.js";
import { trierLignes, useTri } from "../lib/tri.js";

const COULEUR_STATUT = { actif: "vert", hospitalise: "orange", transfere: "bleu", greffe: "violet", arret: "gris", decede: "rouge" };
const voitMedical = (role) => ["super_admin", "admin", "medecin", "infirmier"].includes(role);

/** Mention « modifié, non enregistré » + bouton Enregistrer actif seulement si le formulaire a changé (règle 15). */
function BarreEnregistrement({ modifie, onEnregistrer, desactive }) {
  return (
    <div className="flex items-center justify-between gap-2 mt-2">
      <span className={`text-xs ${modifie ? "text-orange-700 font-medium" : "text-slate-400"}`}>{modifie ? "Modifié, non enregistré" : "Aucune modification"}</span>
      <Bouton icone={Save} variante="principal" disabled={!modifie || desactive} onClick={onEnregistrer}>Enregistrer</Bouton>
    </div>
  );
}

function OngletIdentite({ p, listes, peutEcrire, enregistrer, organismes }) {
  const f = useFormulaire({ organisme_id: p.organisme_id || "", taux: p.taux_prise_en_charge ?? "", nom: p.nom || "", prenom: p.prenom || "", sexe: p.sexe || "", date_naissance: p.date_naissance || "", telephone: p.telephone || "",
    adresse: p.adresse || "", prise_en_charge: p.prise_en_charge || "", numero_assurance: p.numero_assurance || "", pa_nom: p.personne_a_prevenir?.nom || "",
    pa_tel: p.personne_a_prevenir?.telephone || "", pa_lien: p.personne_a_prevenir?.lien || "" });
  const v = f.valeurs;
  const envoyer = () => enregistrer({ nom: v.nom, prenom: v.prenom, sexe: v.sexe, date_naissance: v.date_naissance, telephone: v.telephone, adresse: v.adresse,
    prise_en_charge: v.prise_en_charge, numero_assurance: v.numero_assurance, ...(organismes.length || v.organisme_id ? { organisme_id: v.organisme_id } : {}), taux_prise_en_charge: v.taux === "" ? null : v.taux, personne_a_prevenir: { nom: v.pa_nom, telephone: v.pa_tel, lien: v.pa_lien } }, f.reinitialiser, v);
  return (
    <fieldset disabled={!peutEcrire}>
      <Texte libelle="Nom" valeur={v.nom} onChange={(x) => f.maj("nom", x)} placeholder="BADINI" />
      <Texte libelle="Prénom" valeur={v.prenom} onChange={(x) => f.maj("prenom", x)} placeholder="Awa" />
      <Liste libelle="Sexe" valeur={v.sexe} onChange={(x) => f.maj("sexe", x)} options={[{ valeur: "F", libelle: "Féminin" }, { valeur: "M", libelle: "Masculin" }]} />
      <Texte libelle="Date de naissance" type="date" valeur={v.date_naissance} onChange={(x) => f.maj("date_naissance", x)} />
      <Texte libelle="Téléphone" valeur={v.telephone} onChange={(x) => f.maj("telephone", x)} />
      <Texte libelle="Adresse" valeur={v.adresse} onChange={(x) => f.maj("adresse", x)} />
      <Liste libelle="Prise en charge" valeur={v.prise_en_charge} onChange={(x) => f.maj("prise_en_charge", x)} options={listes.prises_en_charge} />
      <Texte libelle="Numéro d'assurance" valeur={v.numero_assurance} onChange={(x) => f.maj("numero_assurance", x)} />
      {organismes.length > 0 && <Liste libelle="Organisme payeur" valeur={v.organisme_id} onChange={(x) => f.maj("organisme_id", x)} options={organismes.map((o) => ({ valeur: o.id, libelle: `${o.nom} (${o.taux} %)` }))} vide="Aucun (paiement direct)" />}
      {organismes.length > 0 && <Texte libelle="Taux de prise en charge personnalisé (%)" type="number" valeur={v.taux} onChange={(x) => f.maj("taux", x)} aide="Vide : taux de l'organisme." />}
      <p className="text-sm font-medium mb-1 mt-2">Personne à prévenir</p>
      <Texte libelle="Nom" valeur={v.pa_nom} onChange={(x) => f.maj("pa_nom", x)} placeholder="BADINI Issa" />
      <Texte libelle="Téléphone" valeur={v.pa_tel} onChange={(x) => f.maj("pa_tel", x)} />
      <Texte libelle="Lien" valeur={v.pa_lien} onChange={(x) => f.maj("pa_lien", x)} placeholder="Époux, fils…" />
      {peutEcrire && <BarreEnregistrement modifie={f.modifie} onEnregistrer={envoyer} desactive={!v.nom || !v.prenom || !v.sexe || !v.date_naissance} />}
    </fieldset>
  );
}

function OngletMedical({ p, listes, peutEcrire, enregistrer }) {
  const s = p.serologies || {};
  const f = useFormulaire({ statut: p.statut || "actif", groupe_sanguin: p.groupe_sanguin || "", cause_irc: p.cause_irc || "", date_debut_dialyse: p.date_debut_dialyse || "",
    poids_sec: p.poids_sec ?? "", vhb: s.vhb || "inconnu", vhc: s.vhc || "inconnu", vih: s.vih || "inconnu", allergies: p.allergies || "", antecedents: p.antecedents || "" });
  const v = f.valeurs;
  const envoyer = () => enregistrer({ statut: v.statut, groupe_sanguin: v.groupe_sanguin, cause_irc: v.cause_irc, date_debut_dialyse: v.date_debut_dialyse,
    poids_sec: v.poids_sec === "" ? null : v.poids_sec, serologies: { vhb: v.vhb, vhc: v.vhc, vih: v.vih }, allergies: v.allergies, antecedents: v.antecedents }, f.reinitialiser, v);
  const sero = (cle) => <Liste libelle={"Sérologie " + cle.toUpperCase()} valeur={v[cle]} onChange={(x) => f.maj(cle, x)} options={listes.serologies} />;
  return (
    <fieldset disabled={!peutEcrire}>
      <Liste libelle="Statut du patient" valeur={v.statut} onChange={(x) => f.maj("statut", x)} options={listes.statuts} />
      <Liste libelle="Groupe sanguin" valeur={v.groupe_sanguin} onChange={(x) => f.maj("groupe_sanguin", x)} options={listes.groupes} />
      <Liste libelle="Cause de l'insuffisance rénale" valeur={v.cause_irc} onChange={(x) => f.maj("cause_irc", x)} options={listes.causes} />
      <Texte libelle="Début de la dialyse" type="date" valeur={v.date_debut_dialyse} onChange={(x) => f.maj("date_debut_dialyse", x)} />
      <Texte libelle="Poids sec (kg)" type="number" step="0.1" valeur={v.poids_sec} onChange={(x) => f.maj("poids_sec", x)} />
      <div className="grid grid-cols-3 gap-2">{sero("vhb")}{sero("vhc")}{sero("vih")}</div>
      <Texte libelle="Allergies" valeur={v.allergies} onChange={(x) => f.maj("allergies", x)} />
      <Texte libelle="Antécédents" valeur={v.antecedents} onChange={(x) => f.maj("antecedents", x)} />
      {peutEcrire && <BarreEnregistrement modifie={f.modifie} onEnregistrer={envoyer} />}
    </fieldset>
  );
}

function OngletPrescription({ p, listes, peutEcrire, enregistrer }) {
  const x = p.prescription || {};
  const b = x.bain || {};
  const f = useFormulaire({ duree_min: x.duree_min ?? "", frequence_semaine: x.frequence_semaine ?? "", jours: x.jours || [], creneau: x.creneau || "", dialyseur: x.dialyseur || "",
    debit_sang: x.debit_sang ?? "", debit_dialysat: x.debit_dialysat ?? "", anticoagulation: x.anticoagulation || "", heparine_ui: x.heparine_ui ?? "",
    k: b.potassium ?? "", ca: b.calcium ?? "", na: b.sodium ?? "", hco3: b.bicarbonate ?? "", notes: x.notes || "" });
  const v = f.valeurs;
  const bascule = (j) => f.maj("jours", v.jours.includes(j) ? v.jours.filter((y) => y !== j) : [...v.jours, j]);
  const envoyer = () => enregistrer({ prescription: { duree_min: v.duree_min, frequence_semaine: v.frequence_semaine, jours: v.jours, creneau: v.creneau, dialyseur: v.dialyseur,
    debit_sang: v.debit_sang, debit_dialysat: v.debit_dialysat, anticoagulation: v.anticoagulation, heparine_ui: v.heparine_ui,
    bain: { potassium: v.k, calcium: v.ca, sodium: v.na, bicarbonate: v.hco3 }, notes: v.notes } }, f.reinitialiser, v);
  return (
    <fieldset disabled={!peutEcrire}>
      {!peutEcrire && <p className="text-xs text-slate-500 mb-2">Seul le médecin modifie la prescription.</p>}
      <div className="grid grid-cols-2 gap-2">
        <Texte libelle="Durée (min)" type="number" valeur={v.duree_min} onChange={(y) => f.maj("duree_min", y)} />
        <Texte libelle="Séances / semaine" type="number" valeur={v.frequence_semaine} onChange={(y) => f.maj("frequence_semaine", y)} />
      </div>
      <p className="text-sm font-medium mb-1">Jours de dialyse</p>
      <div className="flex flex-wrap gap-x-4 mb-2">{listes.jours.map((j) => <Case key={j} libelle={j[0].toUpperCase() + j.slice(1)} valeur={v.jours.includes(j)} onChange={() => bascule(j)} />)}</div>
      <Liste libelle="Créneau habituel" valeur={v.creneau} onChange={(y) => f.maj("creneau", y)} options={listes.creneaux} />
      <Texte libelle="Dialyseur" valeur={v.dialyseur} onChange={(y) => f.maj("dialyseur", y)} placeholder="FX60" />
      <div className="grid grid-cols-2 gap-2">
        <Texte libelle="Débit sang (ml/min)" type="number" valeur={v.debit_sang} onChange={(y) => f.maj("debit_sang", y)} />
        <Texte libelle="Débit dialysat (ml/min)" type="number" valeur={v.debit_dialysat} onChange={(y) => f.maj("debit_dialysat", y)} />
      </div>
      <Liste libelle="Anticoagulation" valeur={v.anticoagulation} onChange={(y) => f.maj("anticoagulation", y)} options={listes.anticoagulations} />
      <Texte libelle="Héparine (UI)" type="number" valeur={v.heparine_ui} onChange={(y) => f.maj("heparine_ui", y)} />
      <p className="text-sm font-medium mb-1">Bain de dialyse</p>
      <div className="grid grid-cols-4 gap-2">
        <Texte libelle="K⁺" type="number" step="0.1" valeur={v.k} onChange={(y) => f.maj("k", y)} />
        <Texte libelle="Ca²⁺" type="number" step="0.05" valeur={v.ca} onChange={(y) => f.maj("ca", y)} />
        <Texte libelle="Na⁺" type="number" valeur={v.na} onChange={(y) => f.maj("na", y)} />
        <Texte libelle="HCO₃⁻" type="number" valeur={v.hco3} onChange={(y) => f.maj("hco3", y)} />
      </div>
      <Texte libelle="Notes du médecin" valeur={v.notes} onChange={(y) => f.maj("notes", y)} />
      {peutEcrire && <BarreEnregistrement modifie={f.modifie} onEnregistrer={envoyer} />}
    </fieldset>
  );
}

function OngletAcces({ p, listes, peutEcrire, recharger }) {
  const { avecToast } = useApp();
  const [form, setForm] = useState({ type: "", localisation: "", date_pose: "", remarques: "" });
  const ajouter = async () => {
    await avecToast("Ajout de l'accès", () => api(`/patients/${p.id}/acces`, { methode: "POST", corps: form }), () => "Accès vasculaire ajouté");
    setForm({ type: "", localisation: "", date_pose: "", remarques: "" }); await recharger();
  };
  const retirer = async (a) => {
    await avecToast("Retrait de l'accès", () => api(`/patients/${p.id}/acces/${a.id}`, { methode: "PUT", corps: { actif: false } }), () => "Accès retiré");
    await recharger();
  };
  return (
    <div>
      <ul className="space-y-2 mb-4">
        {(p.acces_vasculaires || []).map((a) => (
          <li key={a.id} className="flex items-center gap-2 rounded-lg ring-1 ring-encre/10 px-3 py-2 text-sm">
            <div className="flex-1"><div className="font-medium">{a.type}</div><div className="text-slate-600">{a.localisation}{a.date_pose && ` · posé le ${dateFr(a.date_pose)}`}{a.remarques && ` · ${a.remarques}`}</div></div>
            {a.actif ? <Pastille couleur="vert">En service</Pastille> : <Pastille>Retiré {dateFr(a.date_retrait)}</Pastille>}
            {peutEcrire && a.actif && <BoutonIcone icone={Trash2} libelle="Retirer cet accès" couleur="text-rose-600" onClick={() => retirer(a)} />}
          </li>
        ))}
        {!(p.acces_vasculaires || []).length && <li className="text-sm text-slate-500">Aucun accès vasculaire enregistré.</li>}
      </ul>
      {peutEcrire && (
        <div className="rounded-xl bg-slate-50 p-3">
          <p className="text-sm font-medium mb-2">Ajouter un accès</p>
          <Liste libelle="Type" valeur={form.type} onChange={(x) => setForm({ ...form, type: x })} options={listes.types_acces} />
          <Texte libelle="Localisation" valeur={form.localisation} onChange={(x) => setForm({ ...form, localisation: x })} placeholder="Avant-bras gauche" />
          <Texte libelle="Date de pose" type="date" valeur={form.date_pose} onChange={(x) => setForm({ ...form, date_pose: x })} />
          <Texte libelle="Remarques" valeur={form.remarques} onChange={(x) => setForm({ ...form, remarques: x })} />
          <Bouton icone={Plus} variante="vert" disabled={!form.type || !form.localisation} onClick={ajouter}>Ajouter l'accès</Bouton>
        </div>
      )}
    </div>
  );
}

function OngletSeances({ p }) {
  const [lignes, setLignes] = useState(null);
  useEffect(() => { api(`/seances?patient_id=${p.id}`).then((x) => setLignes([...x].reverse())).catch(() => setLignes([])); }, [p.id]);
  if (!lignes) return <span className="jauge" />;
  return (
    <ul className="space-y-1.5 text-sm">
      {lignes.map((s) => (
        <li key={s.id} className="flex items-center gap-2 rounded-lg ring-1 ring-encre/10 px-3 py-1.5">
          <span className="tabular-nums w-24">{dateFr(s.date)}</span><span className="w-14 capitalize">{s.creneau}</span><span className="flex-1">{s.poste_nom}</span>
          {s.alertes?.some((a) => a.niveau === "critique") && <AlertTriangle size={16} className="text-rose-600" aria-label="Alerte critique" />}
          <Pastille couleur={{ terminee: "vert", en_cours: "orange", planifiee: "bleu", annulee: "gris", absente: "rouge" }[s.statut]}>{s.statut_libelle}</Pastille>
        </li>
      ))}
      {!lignes.length && <li className="text-slate-500">Aucune séance.</li>}
    </ul>
  );
}

function Dossier({ id, onFermer, onChange }) {
  const { utilisateur, avecToast, toast } = useApp();
  const listes = useListes();
  const [p, setP] = useState(null);
  const [onglet, setOnglet] = useState("identite");
  const medical = voitMedical(utilisateur.role);
  const [organismes, setOrganismes] = useState([]);
  // La liste des organismes n'est lue que par les rôles de la caisse (le serveur refuse les autres : on ignore l'erreur).
  useEffect(() => { if (["secretariat", "admin", "super_admin"].includes(utilisateur.role)) api("/facturation/organismes").then(setOrganismes).catch(() => {}); }, [utilisateur.role]);
  const charger = useCallback(() => api(`/patients/${id}`).then(setP), [id]);
  // `onFermer` change à chaque rendu du parent : on le garde dans une référence pour ne recharger (et journaliser l'ouverture) qu'une seule fois.
  const fermerRef = useRef(onFermer);
  fermerRef.current = onFermer;
  useEffect(() => { charger().catch((e) => { toast(e.message, "erreur"); fermerRef.current(); }); }, [charger, toast]);
  if (!p) return <Modal titre="Dossier du patient" onFermer={onFermer} large><div className="py-8 flex justify-center"><span className="jauge" /></div></Modal>;

  // Envoi d'une partie du dossier ; remet l'indicateur « modifié » à zéro après enregistrement réussi.
  const enregistrer = async (corps, reinit, valeurs) => {
    const maj = await avecToast("Enregistrement du dossier", () => api(`/patients/${id}`, { methode: "PUT", corps }), () => "Dossier enregistré");
    setP(maj); reinit?.(valeurs); onChange();
  };
  const peutIdentite = ["secretariat", "medecin", "infirmier", "admin", "super_admin"].includes(utilisateur.role);
  const peutMedical = ["medecin", "infirmier", "admin", "super_admin"].includes(utilisateur.role);
  const peutPrescrire = ["medecin", "admin", "super_admin"].includes(utilisateur.role);
  const onglets = [["identite", "Identité"], ...(medical ? [["medical", "Médical"], ["prescription", "Prescription"], ["acces", "Accès vasculaires"], ["bilans", "Bilans"], ["seances", "Séances"]] : [])];
  return (
    <Modal titre={`${p.nom} ${p.prenom} — ${p.code}`} large onFermer={onFermer} pied={<Bouton onClick={onFermer}>Fermer</Bouton>}>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Pastille couleur={COULEUR_STATUT[p.statut]}>{p.statut_libelle}</Pastille>
        <span className="text-sm text-slate-600">{p.age != null && `${p.age} ans`}{p.poids_sec ? ` · poids sec ${nb(p.poids_sec)} kg` : ""}</span>
        {medical && Object.values(p.serologies || {}).includes("positif") && <Pastille couleur="rouge" icone={AlertTriangle}>Sérologie positive</Pastille>}
        {medical && p.allergies && <Pastille couleur="orange" icone={AlertTriangle}>Allergies</Pastille>}
      </div>
      <div className="flex gap-1 border-b border-slate-200 mb-3 overflow-x-auto">
        {onglets.map(([k, l]) => (
          <button key={k} onClick={() => setOnglet(k)} className={`px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 ${onglet === k ? "border-turquoise-600 text-turquoise-700" : "border-transparent text-slate-500 hover:text-nuit"}`}>{l}</button>
        ))}
      </div>
      {onglet === "identite" && <OngletIdentite p={p} listes={listes} peutEcrire={peutIdentite} enregistrer={enregistrer} organismes={organismes} />}
      {onglet === "medical" && <OngletMedical p={p} listes={listes} peutEcrire={peutMedical} enregistrer={enregistrer} />}
      {onglet === "prescription" && <OngletPrescription p={p} listes={listes} peutEcrire={peutPrescrire} enregistrer={enregistrer} />}
      {onglet === "acces" && <OngletAcces p={p} listes={listes} peutEcrire={peutMedical} recharger={charger} />}
      {onglet === "bilans" && <Bilans patient={p} peutEcrire={peutMedical} />}
      {onglet === "seances" && <OngletSeances p={p} />}
    </Modal>
  );
}

function NouveauPatient({ listes, onFermer, onCree }) {
  const { avecToast } = useApp();
  const f = useFormulaire({ nom: "", prenom: "", sexe: "", date_naissance: "", telephone: "", prise_en_charge: "" });
  const v = f.valeurs;
  const creer = async (forcer = false) => {
    try {
      const p = await avecToast("Création du patient", () => api("/patients", { methode: "POST", corps: { ...v, forcer } }), (x) => `Patient ${x.code} créé`);
      onCree(p);
    } catch (e) {
      if (e.statut === 409 && window.confirm("Un patient de même nom, prénom et date de naissance existe déjà. Créer quand même ?")) await creer(true);
    }
  };
  return (
    <Modal titre="Nouveau patient" onFermer={onFermer} pied={<><Bouton onClick={onFermer}>Annuler</Bouton>
      <Bouton icone={Save} variante="principal" disabled={!v.nom || !v.prenom || !v.sexe || !v.date_naissance} onClick={() => creer()}>Enregistrer</Bouton></>}>
      <Texte libelle="Nom" valeur={v.nom} onChange={(x) => f.maj("nom", x)} placeholder="BADINI" />
      <Texte libelle="Prénom" valeur={v.prenom} onChange={(x) => f.maj("prenom", x)} placeholder="Awa" />
      <Liste libelle="Sexe" valeur={v.sexe} onChange={(x) => f.maj("sexe", x)} options={[{ valeur: "F", libelle: "Féminin" }, { valeur: "M", libelle: "Masculin" }]} />
      <Texte libelle="Date de naissance" type="date" valeur={v.date_naissance} onChange={(x) => f.maj("date_naissance", x)} />
      <Texte libelle="Téléphone" valeur={v.telephone} onChange={(x) => f.maj("telephone", x)} />
      <Liste libelle="Prise en charge" valeur={v.prise_en_charge} onChange={(x) => f.maj("prise_en_charge", x)} options={listes.prises_en_charge} />
    </Modal>
  );
}

export default function Patients() {
  const { utilisateur, avecToast, toast } = useApp();
  const listes = useListes();
  const [lignes, setLignes] = useState([]);
  const [q, setQ] = useState("");
  const [statut, setStatut] = useState("actif");
  const [ouvert, setOuvert] = useState(null);
  const [nouveau, setNouveau] = useState(false);
  const [selection, setSelection] = useState(null);
  const tri = useTri();
  const medical = voitMedical(utilisateur.role);
  const charger = useCallback(() => api(`/patients?q=${encodeURIComponent(q)}&statut=${statut}`).then(setLignes), [q, statut]);
  useEffect(() => { const t = setTimeout(() => charger().catch((e) => toast(e.message, "erreur")), 250); return () => clearTimeout(t); }, [charger, toast]);
  const affichees = trierLignes(lignes, tri.cle, tri.sens);
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h1 className="text-2xl font-semibold">Patients</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation des patients", charger, () => "Liste des patients actualisée")}>Actualiser</Bouton>
          {["secretariat", "medecin", "infirmier", "admin", "super_admin"].includes(utilisateur.role) && <Bouton icone={Plus} variante="principal" onClick={() => setNouveau(true)}>Nouveau patient</Bouton>}
        </div>
      </div>
      <div className="grid sm:grid-cols-2 gap-3 max-w-2xl">
        <div className="relative mb-3"><Search size={16} className="absolute left-3 top-3 text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher : nom, prénom, code, téléphone" className="w-full rounded-lg border border-slate-300 pl-9 pr-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500" /></div>
        <Liste libelle="" valeur={statut} onChange={setStatut} options={listes.statuts} vide="Tous les statuts" />
      </div>
      <div className="overflow-x-auto rounded-xl ring-1 ring-encre/10 bg-white">
        <table className="tableau">
          <thead><tr>
            <ThTri cle="code" tri={tri}>Code</ThTri><ThTri cle="nom" tri={tri}>Nom</ThTri><ThTri cle="prenom" tri={tri}>Prénom</ThTri><ThTri cle="sexe" tri={tri}>Sexe</ThTri>
            <ThTri cle="age" tri={tri} numerique>Âge</ThTri><ThTri cle="telephone" tri={tri}>Téléphone</ThTri>
            {medical && <ThTri cle="poids_sec" tri={tri} numerique>Poids sec (kg)</ThTri>}<ThTri cle="statut_libelle" tri={tri}>Statut</ThTri><th>Dossier</th>
          </tr></thead>
          <tbody>
            {affichees.map((p) => (
              <tr key={p.id} onClick={() => setSelection(p.id)} onDoubleClick={() => setOuvert(p.id)} className={selection === p.id ? "ligne-selectionnee" : ""}>
                <td className="font-semibold text-emeraude whitespace-nowrap">{p.code}</td>
                <td className="font-medium">{p.nom} {p.serologie_positive && <AlertTriangle size={14} className="inline text-rose-600" aria-label="Sérologie positive" title="Sérologie positive" />}</td>
                <td>{p.prenom}</td><td>{p.sexe}</td><td className="num">{p.age}</td><td>{p.telephone}</td>
                {medical && <td className="num">{nb(p.poids_sec)}</td>}
                <td><Pastille couleur={COULEUR_STATUT[p.statut]}>{p.statut_libelle}</Pastille></td>
                <td><BoutonIcone icone={FolderOpen} libelle="Ouvrir le dossier" onClick={() => setOuvert(p.id)} /></td>
              </tr>
            ))}
            {!affichees.length && <tr><td colSpan={9} className="text-center text-slate-500 py-6">Aucun patient.</td></tr>}
          </tbody>
        </table>
      </div>
      {ouvert && <Dossier id={ouvert} onFermer={() => setOuvert(null)} onChange={charger} />}
      {nouveau && <NouveauPatient listes={listes} onFermer={() => setNouveau(false)} onCree={(p) => { setNouveau(false); charger(); setOuvert(p.id); }} />}
    </div>
  );
}
