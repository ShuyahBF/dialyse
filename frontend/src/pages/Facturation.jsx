// Facturation et prise en charge : factures (paiements, PDF), tarifs, organismes payeurs, synthèse d'une période, en-tête de la clinique.
// Montants : vert = encaissé, rouge = dû ; alignés à droite. Paramétrage (tarifs, organismes, en-tête, annulation) : administration.
import { Ban, Banknote, FileText, Pencil, Plus, Receipt, RefreshCw, Save, Wand2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Case, Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import PdfInterne from "../composants/PdfInterne.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { aujourdhui, dateFr, fcfa } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

const COULEUR = { emise: "orange", partielle: "bleu", payee: "vert", annulee: "gris" };
const debutMois = () => aujourdhui().slice(0, 8) + "01";

function Factures({ admin, listes }) {
  const { avecToast, toast } = useApp();
  const [lignes, setLignes] = useState([]);
  const [statut, setStatut] = useState("");
  const [du, setDu] = useState(debutMois());
  const [au, setAu] = useState(aujourdhui());
  const [ouverte, setOuverte] = useState(null);
  const [pdf, setPdf] = useState(null);
  const [selection, setSelection] = useState(null);
  const [pay, setPay] = useState({ payeur: "patient", montant: "", mode: "Espèces", reference: "" });
  const [motif, setMotif] = useState("");
  const tri = useTri();
  const charger = useCallback(async () => setLignes(await api(`/factures?du=${du}&au=${au}${statut ? "&statut=" + statut : ""}`)), [du, au, statut]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  // Le payeur proposé est celui qui a encore un reste à payer (patient d'abord).
  useEffect(() => { if (ouverte) setPay((p) => ({ ...p, payeur: ouverte.reste_patient > 0 || !ouverte.organisme_id ? "patient" : "organisme" })); }, [ouverte]);
  const rafraichir = async (id) => { await charger(); setOuverte(await api(`/factures/${id}`)); };

  async function generer() {
    await avecToast("Facturation des séances terminées", () => api("/factures/generer", { methode: "POST", corps: { du, au } }), (r) => `${r.creees} facture(s) créée(s), ${r.deja_facturees} déjà facturée(s)`);
    await charger();
  }
  async function payer() {
    const f = await avecToast("Enregistrement du paiement", () => api(`/factures/${ouverte.id}/paiements`, { methode: "POST", corps: pay }), () => "Paiement enregistré");
    setPay({ ...pay, montant: "", reference: "" }); setOuverte(f); await charger();
  }
  async function annuler() {
    await avecToast("Annulation de la facture", () => api(`/factures/${ouverte.id}/annuler`, { methode: "POST", corps: { motif } }), () => "Facture annulée");
    setMotif(""); await rafraichir(ouverte.id);
  }
  const affichees = trierLignes(lignes, tri.cle, tri.sens);
  return (
    <div>
      <div className="flex flex-wrap items-end gap-3 mb-3">
        <div><Texte libelle="Du" type="date" valeur={du} onChange={setDu} /></div>
        <div><Texte libelle="Au" type="date" valeur={au} onChange={setAu} /></div>
        <div className="min-w-[12rem]"><Liste libelle="Statut" valeur={statut} onChange={setStatut} options={listes.statuts} vide="Tous les statuts" /></div>
        <div className="mb-3 flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation des factures", charger, () => "Factures actualisées")}>Actualiser</Bouton>
          <Bouton icone={Wand2} variante="orange" onClick={generer}>Facturer les séances terminées</Bouton>
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="tableau">
          <thead><tr>
            <ThTri cle="numero" tri={tri}>N°</ThTri><ThTri cle="date" tri={tri}>Date</ThTri><ThTri cle="patient_nom" tri={tri}>Patient</ThTri><ThTri cle="organisme_nom" tri={tri}>Organisme</ThTri>
            <ThTri cle="total" tri={tri} numerique>Total</ThTri><ThTri cle="reste" tri={tri} numerique>Reste à payer</ThTri><ThTri cle="statut_libelle" tri={tri}>Statut</ThTri><th>Facture</th>
          </tr></thead>
          <tbody>
            {affichees.map((f) => (
              <tr key={f.id} onClick={() => setSelection(f.id)} onDoubleClick={() => setOuverte(f)} className={selection === f.id ? "ligne-selectionnee" : ""}>
                <td className="font-semibold text-sky-800 whitespace-nowrap">{f.numero}</td><td>{dateFr(f.date)}</td><td className="font-medium">{f.patient_nom}</td><td>{f.organisme_nom}</td>
                <td className="num">{fcfa(f.total)}</td><td className={`num font-semibold ${f.reste > 0 ? "text-rose-700" : "text-emerald-700"}`}>{fcfa(f.reste)}</td>
                <td><Pastille couleur={COULEUR[f.statut]}>{f.statut_libelle}</Pastille></td>
                <td className="whitespace-nowrap"><BoutonIcone icone={Receipt} libelle="Ouvrir la facture et les paiements" onClick={() => setOuverte(f)} />
                  <BoutonIcone icone={FileText} libelle="Afficher le PDF" couleur="text-rose-600" onClick={() => setPdf(f)} /></td>
              </tr>
            ))}
            {!affichees.length && <tr><td colSpan={8} className="text-center text-slate-500 py-6">Aucune facture sur la période.</td></tr>}
          </tbody>
        </table>
      </div>
      {ouverte && (
        <Modal titre={`Facture ${ouverte.numero}`} large onFermer={() => setOuverte(null)} pied={<><Bouton icone={FileText} onClick={() => setPdf(ouverte)}>Afficher le PDF</Bouton><Bouton onClick={() => setOuverte(null)}>Fermer</Bouton></>}>
          <div className="flex flex-wrap items-center gap-2 mb-3 text-sm"><Pastille couleur={COULEUR[ouverte.statut]}>{ouverte.statut_libelle}</Pastille>
            <span><b>{ouverte.patient_nom}</b> ({ouverte.patient_code}) · séance du {dateFr(ouverte.date)}</span>
            {ouverte.organisme_nom && <span>· {ouverte.organisme_nom} — prise en charge {ouverte.taux} %</span>}</div>
          <table className="tableau mb-3"><thead><tr><th>Désignation</th><th className="num">Qté</th><th className="num">Prix</th><th className="num">Total</th></tr></thead>
            <tbody>{ouverte.lignes.map((l) => <tr key={l.id}><td>{l.libelle}</td><td className="num">{l.quantite}</td><td className="num">{fcfa(l.prix_unitaire)}</td><td className="num">{fcfa(l.total)}</td></tr>)}</tbody></table>
          <div className="grid grid-cols-3 gap-2 text-sm mb-3">
            <div className="rounded-lg bg-slate-50 p-2"><div className="text-slate-500">Total</div><div className="font-semibold tabular-nums">{fcfa(ouverte.total)}</div></div>
            <div className="rounded-lg bg-slate-50 p-2"><div className="text-slate-500">Organisme</div><div className="tabular-nums">{fcfa(ouverte.part_organisme)} <span className={ouverte.reste_organisme ? "text-rose-700" : "text-emerald-700"}>(reste {fcfa(ouverte.reste_organisme)})</span></div></div>
            <div className="rounded-lg bg-slate-50 p-2"><div className="text-slate-500">Patient</div><div className="tabular-nums">{fcfa(ouverte.part_patient)} <span className={ouverte.reste_patient ? "text-rose-700" : "text-emerald-700"}>(reste {fcfa(ouverte.reste_patient)})</span></div></div>
          </div>
          {ouverte.paiements.length > 0 && <ul className="mb-3 text-sm space-y-1">{ouverte.paiements.map((p) => <li key={p.id} className="flex gap-2"><Banknote size={16} className="text-emerald-600 mt-0.5" />
            <span>{dateFr(p.date)} — {p.payeur === "patient" ? "Patient" : "Organisme"} — {p.mode}{p.reference && ` (${p.reference})`} :</span><b className="text-emerald-700 tabular-nums">{fcfa(p.montant)}</b></li>)}</ul>}
          {ouverte.statut !== "annulee" && ouverte.reste > 0 && (
            <section className="rounded-xl border border-emerald-200 p-3 mb-3">
              <h3 className="font-semibold mb-2 flex items-center gap-2 text-emerald-800"><Banknote size={16} /> Enregistrer un paiement</h3>
              <div className="grid grid-cols-2 gap-x-2">
                <Liste libelle="Payeur" valeur={pay.payeur} vide="" onChange={(v) => setPay({ ...pay, payeur: v, montant: "" })} options={[{ valeur: "patient", libelle: `Patient (reste ${fcfa(ouverte.reste_patient)})` }, ...(ouverte.organisme_id ? [{ valeur: "organisme", libelle: `Organisme (reste ${fcfa(ouverte.reste_organisme)})` }] : [])]} />
                <Texte libelle="Montant (FCFA)" type="number" valeur={pay.montant} onChange={(v) => setPay({ ...pay, montant: v })} />
                <Liste libelle="Mode" valeur={pay.mode} vide="" onChange={(v) => setPay({ ...pay, mode: v })} options={listes.modes_paiement} />
                <Texte libelle="Référence (facultatif)" valeur={pay.reference} onChange={(v) => setPay({ ...pay, reference: v })} />
              </div>
              <Bouton icone={Save} variante="vert" disabled={!pay.montant} onClick={payer}>Enregistrer le paiement</Bouton>
            </section>
          )}
          {admin && ouverte.statut === "emise" && (
            <section className="rounded-xl border border-rose-200 p-3">
              <h3 className="font-semibold mb-2 flex items-center gap-2 text-rose-800"><Ban size={16} /> Annuler la facture</h3>
              <Texte libelle="Motif (obligatoire)" valeur={motif} onChange={setMotif} />
              <Bouton icone={Ban} variante="rouge" disabled={!motif} onClick={annuler}>Annuler la facture</Bouton>
            </section>
          )}
          {ouverte.annulee && <p className="text-sm text-rose-700">Annulée par {ouverte.annulee_par} : {ouverte.motif_annulation}</p>}
        </Modal>
      )}
      {pdf && <PdfInterne titre={`Facture ${pdf.numero}`} chemin={`/factures/${pdf.id}/pdf`} onFermer={() => setPdf(null)} />}
    </div>
  );
}

function Tarifs({ admin }) {
  const { avecToast, toast } = useApp();
  const [lignes, setLignes] = useState([]);
  const [modal, setModal] = useState(null);
  const tri = useTri();
  const charger = useCallback(async () => setLignes(await api("/facturation/tarifs")), []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  async function enregistrer() {
    const f = modal.form;
    if (modal.tarif) await avecToast("Enregistrement du tarif", () => api(`/facturation/tarifs/${modal.tarif.id}`, { methode: "PUT", corps: f }), () => "Tarif modifié");
    else await avecToast("Création du tarif", () => api("/facturation/tarifs", { methode: "POST", corps: f }), () => "Tarif créé");
    setModal(null); await charger();
  }
  const maj = (k, v) => setModal((m) => ({ ...m, form: { ...m.form, [k]: v } }));
  return (
    <div>
      {admin && <div className="mb-3"><Bouton icone={Plus} variante="principal" onClick={() => setModal({ form: { libelle: "", prix: "", automatique: false, actif: true } })}>Nouveau tarif</Bouton></div>}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="tableau">
        <thead><tr><ThTri cle="libelle" tri={tri}>Acte</ThTri><ThTri cle="prix" tri={tri} numerique>Prix</ThTri><ThTri cle="automatique" tri={tri}>Sur chaque séance</ThTri><ThTri cle="actif" tri={tri}>État</ThTri>{admin && <th>Actions</th>}</tr></thead>
        <tbody>{trierLignes(lignes, tri.cle, tri.sens).map((t) => <tr key={t.id}><td className="font-medium">{t.libelle}</td><td className="num font-semibold">{fcfa(t.prix)}</td>
          <td>{t.automatique ? <Pastille couleur="vert">Automatique</Pastille> : <span className="text-slate-400">—</span>}</td><td>{t.actif ? <Pastille couleur="vert">Actif</Pastille> : <Pastille>Inactif</Pastille>}</td>
          {admin && <td><BoutonIcone icone={Pencil} libelle="Modifier le tarif" onClick={() => setModal({ tarif: t, form: { libelle: t.libelle, prix: t.prix, automatique: t.automatique, actif: t.actif } })} /></td>}</tr>)}
          {!lignes.length && <tr><td colSpan={5} className="text-center text-slate-500 py-6">Aucun tarif. Créez d'abord « Séance d'hémodialyse » en automatique.</td></tr>}</tbody></table></div>
      {modal && <Modal titre={modal.tarif ? "Modifier le tarif" : "Nouveau tarif"} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton><Bouton icone={Save} variante="principal" disabled={!modal.form.libelle || modal.form.prix === ""} onClick={enregistrer}>Enregistrer</Bouton></>}>
        <Texte libelle="Libellé de l'acte" valeur={modal.form.libelle} onChange={(v) => maj("libelle", v)} placeholder="Séance d'hémodialyse" />
        <Texte libelle="Prix (FCFA, entier)" type="number" valeur={modal.form.prix} onChange={(v) => maj("prix", v)} />
        <Case libelle="Facturer automatiquement sur chaque séance" valeur={modal.form.automatique} onChange={(v) => maj("automatique", v)} />
        {modal.tarif && <Case libelle="Tarif actif" valeur={modal.form.actif} onChange={(v) => maj("actif", v)} />}
        <p className="text-xs text-slate-500">Un changement de prix ne modifie pas les factures déjà émises.</p></Modal>}
    </div>
  );
}

function Organismes({ admin, listes }) {
  const { avecToast, toast } = useApp();
  const [lignes, setLignes] = useState([]);
  const [modal, setModal] = useState(null);
  const tri = useTri();
  const charger = useCallback(async () => setLignes(await api("/facturation/organismes")), []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  async function enregistrer() {
    const f = modal.form;
    if (modal.org) await avecToast("Enregistrement de l'organisme", () => api(`/facturation/organismes/${modal.org.id}`, { methode: "PUT", corps: f }), () => "Organisme modifié");
    else await avecToast("Création de l'organisme", () => api("/facturation/organismes", { methode: "POST", corps: f }), () => "Organisme créé");
    setModal(null); await charger();
  }
  const maj = (k, v) => setModal((m) => ({ ...m, form: { ...m.form, [k]: v } }));
  return (
    <div>
      {admin && <div className="mb-3"><Bouton icone={Plus} variante="principal" onClick={() => setModal({ form: { nom: "", type: "", taux: 80, contact: "", actif: true } })}>Nouvel organisme</Bouton></div>}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="tableau">
        <thead><tr><ThTri cle="nom" tri={tri}>Organisme</ThTri><ThTri cle="type" tri={tri}>Type</ThTri><ThTri cle="taux" tri={tri} numerique>Prise en charge</ThTri><ThTri cle="contact" tri={tri}>Contact</ThTri><ThTri cle="actif" tri={tri}>État</ThTri>{admin && <th>Actions</th>}</tr></thead>
        <tbody>{trierLignes(lignes, tri.cle, tri.sens).map((o) => <tr key={o.id}><td className="font-medium text-sky-800">{o.nom}</td><td>{o.type}</td><td className="num font-semibold">{o.taux} %</td><td>{o.contact}</td>
          <td>{o.actif ? <Pastille couleur="vert">Actif</Pastille> : <Pastille>Inactif</Pastille>}</td>
          {admin && <td><BoutonIcone icone={Pencil} libelle="Modifier l'organisme" onClick={() => setModal({ org: o, form: { nom: o.nom, type: o.type, taux: o.taux, contact: o.contact, actif: o.actif } })} /></td>}</tr>)}
          {!lignes.length && <tr><td colSpan={6} className="text-center text-slate-500 py-6">Aucun organisme payeur.</td></tr>}</tbody></table></div>
      {modal && <Modal titre={modal.org ? "Modifier l'organisme" : "Nouvel organisme"} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton><Bouton icone={Save} variante="principal" disabled={!modal.form.nom || !modal.form.type} onClick={enregistrer}>Enregistrer</Bouton></>}>
        <Texte libelle="Nom" valeur={modal.form.nom} onChange={(v) => maj("nom", v)} placeholder="CNSS" />
        <Liste libelle="Type" valeur={modal.form.type} onChange={(v) => maj("type", v)} options={listes.types_organisme} />
        <Texte libelle="Taux de prise en charge (%)" type="number" valeur={modal.form.taux} onChange={(v) => maj("taux", v)} />
        <Texte libelle="Contact" valeur={modal.form.contact} onChange={(v) => maj("contact", v)} />
        {modal.org && <Case libelle="Organisme actif" valeur={modal.form.actif} onChange={(v) => maj("actif", v)} />}</Modal>}
    </div>
  );
}

function Synthese() {
  const { avecToast, toast } = useApp();
  const [du, setDu] = useState(debutMois());
  const [au, setAu] = useState(aujourdhui());
  const [s, setS] = useState(null);
  const charger = useCallback(async () => setS(await api(`/facturation/synthese?du=${du}&au=${au}`)), [du, au]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const Carte = ({ titre, v, c }) => <div className="rounded-xl bg-white border border-slate-200 p-3"><div className="text-sm text-slate-500">{titre}</div><div className={`text-xl font-semibold tabular-nums ${c}`}>{fcfa(v)}</div></div>;
  return (
    <div>
      <div className="flex flex-wrap items-end gap-3 mb-3">
        <div><Texte libelle="Du" type="date" valeur={du} onChange={setDu} /></div><div><Texte libelle="Au" type="date" valeur={au} onChange={setAu} /></div>
        <div className="mb-3"><Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation de la synthèse", charger, () => "Synthèse actualisée")}>Actualiser</Bouton></div>
      </div>
      {s && <>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <Carte titre={`Facturé (${s.nombre} factures)`} v={s.facture} c="text-nuit" /><Carte titre="Encaissé des patients" v={s.encaisse_patients} c="text-emerald-700" />
          <Carte titre="Encaissé des organismes" v={s.encaisse_organismes} c="text-emerald-700" /><Carte titre="Reste à encaisser" v={s.reste} c="text-rose-700" />
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <section><h3 className="font-semibold mb-2">Créances par organisme</h3><table className="tableau"><thead><tr><th>Organisme</th><th className="num">Factures</th><th className="num">Reste dû</th></tr></thead>
            <tbody>{s.creances_organismes.map((o) => <tr key={o.organisme}><td className="font-medium">{o.organisme}</td><td className="num">{o.factures}</td><td className="num text-rose-700 font-semibold">{fcfa(o.reste)}</td></tr>)}
              {!s.creances_organismes.length && <tr><td colSpan={3} className="text-slate-500">Aucune créance.</td></tr>}</tbody></table></section>
          <section><h3 className="font-semibold mb-2">Patients ayant un reste à payer</h3><table className="tableau"><thead><tr><th>Patient</th><th className="num">Factures</th><th className="num">Reste dû</th></tr></thead>
            <tbody>{s.impayes_patients.map((p) => <tr key={p.code}><td className="font-medium">{p.patient} <span className="text-slate-500">({p.code})</span></td><td className="num">{p.factures}</td><td className="num text-rose-700 font-semibold">{fcfa(p.reste)}</td></tr>)}
              {!s.impayes_patients.length && <tr><td colSpan={3} className="text-slate-500">Aucun impayé.</td></tr>}</tbody></table></section>
        </div></>}
    </div>
  );
}

function Entete({ admin }) {
  const { avecToast, toast } = useApp();
  const [f, setF] = useState({ nom: "", adresse: "", telephone: "", identifiant_fiscal: "" });
  const [origine, setOrigine] = useState("");
  useEffect(() => { api("/facturation/clinique").then((x) => { const v = { nom: "", adresse: "", telephone: "", identifiant_fiscal: "", ...x }; setF(v); setOrigine(JSON.stringify(v)); }).catch((e) => toast(e.message, "erreur")); }, [toast]);
  const modifie = JSON.stringify(f) !== origine;
  return (
    <fieldset disabled={!admin} className="max-w-md">
      <Texte libelle="Nom de la clinique" valeur={f.nom} onChange={(v) => setF({ ...f, nom: v })} placeholder="Clinique Philadelphie" />
      <Texte libelle="Adresse" valeur={f.adresse} onChange={(v) => setF({ ...f, adresse: v })} />
      <Texte libelle="Téléphone" valeur={f.telephone} onChange={(v) => setF({ ...f, telephone: v })} />
      <Texte libelle="IFU / RCCM" valeur={f.identifiant_fiscal} onChange={(v) => setF({ ...f, identifiant_fiscal: v })} />
      {admin ? <div className="flex items-center justify-between"><span className={`text-xs ${modifie ? "text-orange-700 font-medium" : "text-slate-400"}`}>{modifie ? "Modifié, non enregistré" : "Aucune modification"}</span>
        <Bouton icone={Save} variante="principal" disabled={!modifie} onClick={async () => { await avecToast("Enregistrement de l'en-tête", () => api("/facturation/clinique", { methode: "PUT", corps: f }), () => "En-tête enregistré"); setOrigine(JSON.stringify(f)); }}>Enregistrer</Bouton></div>
        : <p className="text-xs text-slate-500">Seule l'administration modifie l'en-tête des factures.</p>}
    </fieldset>
  );
}

export default function Facturation() {
  const { utilisateur, toast } = useApp();
  const admin = ["admin", "super_admin"].includes(utilisateur.role);
  const [onglet, setOnglet] = useState("factures");
  const [listes, setListes] = useState({ statuts: [], modes_paiement: [], types_organisme: [] });
  useEffect(() => { api("/facturation/listes").then(setListes).catch((e) => toast(e.message, "erreur")); }, [toast]);
  const onglets = [["factures", "Factures"], ["tarifs", "Tarifs"], ["organismes", "Organismes payeurs"], ["synthese", "Synthèse"], ["entete", "En-tête"]];
  return (
    <div>
      <h1 className="text-2xl font-semibold mb-3">Facturation Et Prise En Charge</h1>
      <div className="flex gap-1 border-b border-slate-200 mb-4 overflow-x-auto">
        {onglets.map(([k, l]) => <button key={k} onClick={() => setOnglet(k)} className={`px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 ${onglet === k ? "border-turquoise-600 text-turquoise-700" : "border-transparent text-slate-500 hover:text-nuit"}`}>{l}</button>)}
      </div>
      {onglet === "factures" && <Factures admin={admin} listes={listes} />}
      {onglet === "tarifs" && <Tarifs admin={admin} />}
      {onglet === "organismes" && <Organismes admin={admin} listes={listes} />}
      {onglet === "synthese" && <Synthese />}
      {onglet === "entete" && <Entete admin={admin} />}
    </div>
  );
}
