// Centre de messagerie WhatsApp du centre (Liluvine / SAWALI) : conversations, contacts, modèles de messages, rappels de séances.
// Envoi de documents : facture du patient, papier à en-tête A4 / A5, fichier PDF ou image. Tout est propre au centre de travail.
import { BellRing, FileText, Save, MessageCircle, Paperclip, Pencil, Plus, RefreshCw, Search, Send, Trash2, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Case, Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateHeureFr } from "../lib/format.js";

const CATEGORIES = [{ valeur: "patient", libelle: "Patient" }, { valeur: "proche", libelle: "Proche d'un patient" }, { valeur: "medecin", libelle: "Médecin" }, { valeur: "fournisseur", libelle: "Fournisseur" }, { valeur: "autre", libelle: "Autre" }];
const ETAT = { en_cours: ["gris", "En cours"], envoye: ["bleu", "Envoyé"], remis: ["vert", "Remis"], lu: ["vert", "Lu"], echec: ["rouge", "Échec"], recu: ["violet", "Reçu"] };

const lireBase64 = (f) => new Promise((ok, ko) => { const l = new FileReader(); l.onload = () => ok(String(l.result).split(",")[1]); l.onerror = () => ko(new Error("Fichier illisible")); l.readAsDataURL(f); });

function Onglets({ onglets, actif, onChoix }) {
  return (
    <div className="mb-3 flex flex-wrap gap-1 border-b border-slate-200">
      {onglets.map(([k, l, n]) => (
        <button key={k} type="button" onClick={() => onChoix(k)} className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-semibold ${actif === k ? "border-citron text-encre" : "border-transparent text-slate-500 hover:text-encre"}`}>
          {l}{n > 0 && <span className="rounded-full bg-citron px-1.5 text-[11px] font-bold text-white">{n}</span>}
        </button>
      ))}
    </div>
  );
}

/** Réglages des notifications AUTOMATIQUES du patient (option activable par centre, comme sur SAWALI). Modifiables par l'administration seulement. */
function NotificationsAuto({ peutRegler }) {
  const { avecToast, toast } = useApp();
  const [orig, setOrig] = useState(null);
  const [f, setF] = useState(null);
  const charger = useCallback(async () => { const p = await api("/messagerie/parametres"); setOrig(p); setF({ actif: p.actif, rappel_heures_avant: p.rappel_heures_avant, evenements: p.evenements }); return p; }, []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  if (!f) return <div className="flex justify-center py-6"><span className="jauge" /></div>;
  const modifie = JSON.stringify(f) !== JSON.stringify({ actif: orig.actif, rappel_heures_avant: orig.rappel_heures_avant, evenements: orig.evenements });
  async function enregistrer() {
    await avecToast("Enregistrement des notifications", () => api("/messagerie/parametres", { methode: "PUT", corps: f }), () => "Notifications automatiques enregistrées");
    await charger();
  }
  return (
    <div className="max-w-xl rounded-2xl bg-white p-4 ring-1 ring-encre/5">
      <p className="mb-3 text-sm text-ardoise">Le centre prévient lui-même ses patients par WhatsApp : rendez-vous pris, annulé, séance terminée, rappel avant la séance, contrôle à renouveler. Les textes se modifient dans « Modèles de messages ». Aucun message ne contient de donnée médicale ; un patient qui a répondu STOP n'en reçoit plus.</p>
      <label className="mb-3 flex items-center gap-3 rounded-xl bg-brume p-3 text-sm font-semibold">
        <input type="checkbox" className="h-5 w-5 accent-emeraude" checked={f.actif} disabled={!peutRegler} onChange={(e) => setF({ ...f, actif: e.target.checked })} />
        Notifications automatiques {f.actif ? <Pastille couleur="vert">Activées pour ce centre</Pastille> : <Pastille>Désactivées</Pastille>}
      </label>
      <Texte libelle="Rappel avant la séance (heures avant le début)" type="number" min={orig.heures_min} max={orig.heures_max} valeur={f.rappel_heures_avant} disabled={!peutRegler || !f.actif}
        onChange={(v) => setF({ ...f, rappel_heures_avant: Number(v) })} aide={`De ${orig.heures_min} à ${orig.heures_max} heures. Le patient reçoit un seul rappel, au plus tôt ce nombre d'heures avant l'heure de sa séance.`} />
      <p className="mb-1 text-xs font-semibold text-ardoise">Événements notifiés</p>
      {orig.liste.map((e) => <Case key={e.cle} libelle={e.libelle} valeur={f.evenements[e.cle]} onChange={(v) => peutRegler && f.actif && setF({ ...f, evenements: { ...f.evenements, [e.cle]: v } })} />)}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Bouton icone={Save} variante="principal" disabled={!peutRegler || !modifie} onClick={enregistrer}>Enregistrer</Bouton>
        {modifie && <span className="text-xs text-orange-700">Modifié, non enregistré</span>}
        {!peutRegler && <span className="text-xs text-slate-500">Réglage réservé à l'administrateur du centre.</span>}
      </div>
    </div>
  );
}

/** Fil de discussion avec un contact + zone d'écriture (modèle, document, envoi). */
function Conversation({ contact, modeles, onChange }) {
  const { avecToast, toast } = useApp();
  const [d, setD] = useState(null);
  const [texte, setTexte] = useState("");
  const [document, setDocument] = useState(null);     // { type: "papier", format } | { type: "facture", id } | { type: "fichier", ... }
  const [factures, setFactures] = useState([]);
  const bas = useRef(null);
  // `onChange` change à CHAQUE rendu du parent : on le garde dans une référence. Sinon `charger` changeait à chaque rendu, l'effet de chargement se relançait en boucle,
  // remettait le message à zéro (impossible de saisir) et réaffichait la jauge sans fin (défaut relevé sur la vidéo du 20/11/2026).
  const surChangement = useRef(onChange);
  surChangement.current = onChange;
  const charger = useCallback(() => api(`/messagerie/contacts/${contact.id}/messages`).then((x) => { setD(x); surChangement.current?.(); }), [contact.id]);
  // Changement de contact : on repart d'une zone d'écriture vide (et SEULEMENT dans ce cas : jamais pendant la saisie).
  useEffect(() => { setD(null); setDocument(null); setTexte(""); }, [contact.id]);
  useEffect(() => {
    charger().catch((e) => toast(e.message, "erreur"));
    const t = setInterval(() => charger().catch(() => {}), 20000);
    return () => clearInterval(t);
  }, [charger, toast]);
  useEffect(() => { bas.current?.scrollIntoView({ block: "end" }); }, [d]);
  useEffect(() => { if (contact.patient_id) api(`/factures?patient_id=${contact.patient_id}`).then((l) => setFactures(l.filter((f) => f.statut !== "annulee").slice(0, 20))).catch(() => setFactures([])); else setFactures([]); }, [contact.patient_id]);

  async function choisirFichier(e) {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    if (!["application/pdf", "image/jpeg", "image/png"].includes(f.type)) return toast("Fichier : PDF, JPEG ou PNG", "erreur");
    if (f.size > 5 * 1024 * 1024) return toast("Fichier trop lourd : 5 Mo au plus", "erreur");
    setDocument({ type: "fichier", mime: f.type, nom: f.name, contenu_base64: await lireBase64(f) });
  }
  async function envoyer() {
    await avecToast("Envoi du message", () => api("/messagerie/envoyer", { methode: "POST", corps: { contact_id: contact.id, texte, document } }), () => "Message transmis à WhatsApp");
    setTexte(""); setDocument(null); await charger();
  }
  const libelleDoc = document?.type === "papier" ? `Papier à en-tête ${document.format}` : document?.type === "facture" ? "Facture" : document?.nom;
  return (
    <div className="flex h-[70dvh] flex-col rounded-xl bg-white ring-1 ring-encre/10">
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
        <div><p className="font-semibold text-emeraude">{contact.nom}</p><p className="text-xs text-slate-500">+{contact.numero}{contact.desinscrit && <span className="ml-2 font-semibold text-rose-700">désinscrit (STOP)</span>}</p></div>
        <BoutonIcone icone={RefreshCw} libelle="Actualiser la conversation" onClick={() => avecToast("Actualisation de la conversation", charger, () => "Conversation actualisée")} />
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto bg-brume p-3">
        {!d ? <div className="flex justify-center py-6"><span className="jauge" /></div> : d.messages.length === 0 ? <p className="py-6 text-center text-sm text-slate-500">Aucun message. Écrivez le premier.</p> :
          d.messages.map((m) => (
            <div key={m.id} className={`flex ${m.sens === "sortant" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm shadow-sm ${m.sens === "sortant" ? "bg-emerald-100" : "bg-white"}`}>
                {m.document && <p className="mb-1 flex items-center gap-1 text-xs font-semibold text-emeraude"><FileText size={13} /> {m.document}</p>}
                {m.texte && <p className="whitespace-pre-wrap">{m.texte}</p>}
                <p className="mt-1 flex items-center justify-end gap-1.5 text-[10px] text-slate-500">{dateHeureFr(m.cree_le)}
                  {m.sens === "sortant" && <Pastille couleur={(ETAT[m.statut] || ETAT.en_cours)[0]}>{(ETAT[m.statut] || ETAT.en_cours)[1]}</Pastille>}</p>
                {m.erreur && <p className="text-[11px] text-rose-700">{m.erreur}</p>}
              </div>
            </div>
          ))}
        <div ref={bas} />
      </div>
      <div className="border-t border-slate-200 p-2">
        {document && <p className="mb-1 flex items-center gap-2 text-xs text-emeraude"><Paperclip size={13} /> {libelleDoc} joint <button type="button" onClick={() => setDocument(null)} aria-label="Retirer le document" className="text-rose-600"><X size={14} /></button></p>}
        <div className="mb-1 flex flex-wrap gap-1.5">
          <select aria-label="Modèle de message" className="rounded-lg border border-slate-300 px-2 py-1 text-xs" value="" onChange={(e) => { const m = modeles.find((x) => x.id === e.target.value); if (m) setTexte(m.texte); }}>
            <option value="">Modèle…</option>{modeles.map((m) => <option key={m.id} value={m.id}>{m.nom}</option>)}</select>
          <select aria-label="Joindre un document" className="rounded-lg border border-slate-300 px-2 py-1 text-xs" value="" onChange={(e) => {
            const v = e.target.value;
            if (v === "A4" || v === "A5") setDocument({ type: "papier", format: v });
            else if (v.startsWith("f:")) setDocument({ type: "facture", id: v.slice(2) });
          }}>
            <option value="">Joindre…</option><option value="A4">Papier à en-tête A4</option><option value="A5">Papier à en-tête A5</option>
            {factures.map((f) => <option key={f.id} value={"f:" + f.id}>Facture {f.numero}</option>)}</select>
          <label className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-slate-300 px-2 py-1 text-xs font-semibold"><Paperclip size={12} /> Fichier…
            <input type="file" accept="application/pdf,image/jpeg,image/png" className="sr-only" onChange={choisirFichier} /></label>
        </div>
        <div className="flex gap-2">
          <textarea value={texte} onChange={(e) => setTexte(e.target.value)} rows={2} maxLength={1000} placeholder="Votre message…" aria-label="Message" disabled={contact.desinscrit}
            className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
          <Bouton icone={Send} variante="principal" disabled={contact.desinscrit || (!texte.trim() && !document)} onClick={envoyer}>Envoyer</Bouton>
        </div>
      </div>
    </div>
  );
}

export default function Messagerie() {
  const { avecToast, toast, rafraichirCompteurs, utilisateur } = useApp();
  const [onglet, setOnglet] = useState("conversations");
  const [etat, setEtat] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [nonLus, setNonLus] = useState({});
  const [modeles, setModeles] = useState([]);
  const [q, setQ] = useState("");
  const [choisi, setChoisi] = useState(null);
  const [modal, setModal] = useState(null);
  const [form, setForm] = useState({});
  const [rappel, setRappel] = useState({ date: new Date(Date.now() + 86400000).toISOString().slice(0, 10), apercu: null });
  const charger = useCallback(async () => {
    const [e, c, n, m] = await Promise.all([api("/messagerie/etat"), api(`/messagerie/contacts?q=${encodeURIComponent(q)}`), api("/messagerie/non-lus"), api("/messagerie/modeles")]);
    setEtat(e); setContacts(c); setNonLus(n); setModeles(m); rafraichirCompteurs?.();
    return c;
  }, [q, rafraichirCompteurs]);
  useEffect(() => { const t = setTimeout(() => charger().catch((e) => toast(e.message, "erreur")), 250); return () => clearTimeout(t); }, [charger, toast]);
  useEffect(() => { const t = setInterval(() => charger().catch(() => {}), 30000); return () => clearInterval(t); }, [charger]);
  useEffect(() => { if (onglet === "rappels") api(`/messagerie/rappels/apercu?date=${rappel.date}`).then((a) => setRappel((r) => ({ ...r, apercu: a }))).catch(() => {}); }, [onglet, rappel.date]);

  const agir = async (enCours, action, ok) => { await avecToast(enCours, action, ok); setModal(null); await charger(); };
  const totalNonLus = Object.values(nonLus).reduce((a, b) => a + b, 0);
  const contactChoisi = contacts.find((c) => c.id === choisi);
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><MessageCircle size={24} className="text-emerald-600" /> Centre De Messagerie WA</h1>
        <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation de la messagerie", charger, (c) => `${c.length} contact(s), ${totalNonLus} message(s) non lu(s)`)}>Actualiser</Bouton>
      </div>
      <BandeauVersion className="mb-3" />
      {etat?.configure && <p className="mb-2 text-xs text-slate-500">Canal d'envoi : {etat.canal === "ligne_centre" ? <b className="text-emerald-700">ligne WhatsApp propre à ce centre</b> : <b>ligne partagée Liluvine (SAWALI)</b>}.</p>}
      {etat && !etat.configure && <p className="mb-3 rounded-lg bg-orange-50 p-3 text-sm text-orange-900">WhatsApp n'est pas encore configuré sur le serveur : saisissez <b>LILUVINE_WA_URL</b> et <b>LILUVINE_WA_HMAC</b> dans Render (clé de l'émetteur « dialyse » créé dans SAWALI). Les contacts et les modèles restent utilisables.</p>}
      <Onglets actif={onglet} onChoix={setOnglet} onglets={[["conversations", "Conversations", totalNonLus], ["contacts", "Contacts", 0], ["modeles", "Modèles de messages", 0], ["rappels", "Rappels de séances", 0], ["auto", "Notifications auto", 0]]} />

      {onglet === "conversations" && (
        <div className="grid gap-3 md:grid-cols-[18rem_1fr]">
          <div>
            <div className="relative mb-2"><Search size={15} className="absolute left-2.5 top-2.5 text-slate-400" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un contact" aria-label="Rechercher un contact" className="w-full rounded-lg border border-slate-300 py-2 pl-8 pr-2 text-sm" /></div>
            <ul className="max-h-[64dvh] overflow-y-auto rounded-xl bg-white ring-1 ring-encre/10">
              {contacts.length === 0 && <li className="p-4 text-center text-sm text-slate-500">Aucun contact. Ouvrez « Contacts » pour importer vos patients.</li>}
              {contacts.map((c) => (
                <li key={c.id}><button type="button" onClick={() => setChoisi(c.id)} className={`flex w-full items-center justify-between gap-2 border-b border-slate-100 px-3 py-2 text-left hover:bg-sky-50 ${choisi === c.id ? "bg-orange-50" : ""}`}>
                  <span className="min-w-0"><span className="block truncate text-sm font-semibold">{c.nom}</span><span className="block truncate text-xs text-slate-500">{c.dernier_extrait || "Aucun message"}</span></span>
                  {nonLus[c.id] > 0 && <span className="shrink-0 rounded-full bg-emerald-600 px-1.5 text-[11px] font-bold text-white" aria-label={`${nonLus[c.id]} non lu(s)`}>{nonLus[c.id]}</span>}</button></li>
              ))}
            </ul>
          </div>
          {contactChoisi ? <Conversation contact={contactChoisi} modeles={modeles} onChange={() => { api("/messagerie/non-lus").then(setNonLus).catch(() => {}); rafraichirCompteurs?.(); }} />
            : <div className="flex h-[40dvh] items-center justify-center rounded-xl bg-white text-sm text-slate-500 ring-1 ring-encre/10">Choisissez une conversation.</div>}
        </div>
      )}

      {onglet === "contacts" && (
        <div>
          <div className="mb-2 flex flex-wrap gap-2">
            <Bouton icone={Plus} variante="principal" onClick={() => { setForm({ categorie: "autre" }); setModal({ type: "contact" }); }}>Nouveau contact</Bouton>
            <Bouton icone={UserPlus} onClick={() => agir("Import des patients", () => api("/messagerie/contacts/importer-patients", { methode: "POST", corps: {} }), (r) => `${r.crees} contact(s) créé(s), ${r.sans_numero_valide} patient(s) sans numéro valide`)}>Importer les patients</Bouton>
          </div>
          <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
            <table className="tableau"><thead><tr><th>Nom</th><th>Numéro</th><th>Catégorie</th><th>État</th><th>Dernier message</th><th>Actions</th></tr></thead>
              <tbody>{contacts.map((c) => (
                <tr key={c.id}><td className="font-medium text-emeraude">{c.nom}</td><td className="tabular-nums">+{c.numero}</td><td>{CATEGORIES.find((x) => x.valeur === c.categorie)?.libelle}</td>
                  <td>{c.desinscrit ? <Pastille couleur="rouge">Désinscrit (STOP)</Pastille> : <Pastille couleur="vert">Actif</Pastille>}</td><td className="tabular-nums">{c.dernier_le ? dateHeureFr(c.dernier_le) : "—"}</td>
                  <td className="whitespace-nowrap">
                    <BoutonIcone icone={MessageCircle} libelle="Ouvrir la conversation" couleur="text-emerald-600" onClick={() => { setChoisi(c.id); setOnglet("conversations"); }} />
                    <BoutonIcone icone={Pencil} libelle="Modifier le contact" onClick={() => { setForm({ nom: c.nom, numero: c.numero, categorie: c.categorie }); setModal({ type: "contact", c }); }} />
                    <BoutonIcone icone={Trash2} libelle="Supprimer le contact" couleur="text-rose-600" onClick={() => { if (window.confirm(`Supprimer ${c.nom} et sa conversation ?`)) agir("Suppression", () => api(`/messagerie/contacts/${c.id}`, { methode: "DELETE" }), () => "Contact supprimé").catch(() => {}); }} /></td></tr>
              ))}</tbody></table>
          </div>
        </div>
      )}

      {onglet === "modeles" && (
        <div>
          <div className="mb-2"><Bouton icone={Plus} variante="principal" onClick={() => { setForm({}); setModal({ type: "modele" }); }}>Nouveau modèle</Bouton></div>
          <p className="mb-2 text-xs text-slate-500">Variables : {"{prenom} {nom} {centre} {date} {creneau} {poste}"}</p>
          <div className="space-y-2">{modeles.map((m) => (
            <div key={m.id} className="flex items-start justify-between gap-2 rounded-xl bg-white p-3 ring-1 ring-encre/10"><div><p className="font-semibold text-emeraude">{m.nom}</p><p className="whitespace-pre-wrap text-sm text-slate-600">{m.texte}</p></div>
              <span className="whitespace-nowrap"><BoutonIcone icone={Pencil} libelle="Modifier le modèle" onClick={() => { setForm({ nom: m.nom, texte: m.texte }); setModal({ type: "modele", m }); }} />
                <BoutonIcone icone={Trash2} libelle="Supprimer le modèle" couleur="text-rose-600" onClick={() => agir("Suppression", () => api(`/messagerie/modeles/${m.id}`, { methode: "DELETE" }), () => "Modèle supprimé")} /></span></div>))}</div>
        </div>
      )}

      {onglet === "rappels" && (
        <div className="max-w-xl rounded-2xl bg-white p-4 ring-1 ring-encre/5">
          <p className="mb-3 text-sm text-ardoise">Envoie à chaque patient qui a une séance planifiée ce jour-là un rappel WhatsApp (modèle « Rappel de séance »). Le patient répond <b>1</b> pour confirmer ou <b>2</b> s'il est empêché : la réponse apparaît dans le calendrier.</p>
          <Texte libelle="Date des séances" type="date" valeur={rappel.date} onChange={(v) => setRappel({ date: v, apercu: null })} />
          {rappel.apercu && <p className="mb-3 text-sm"><b>{rappel.apercu.a_envoyer}</b> rappel(s) à envoyer sur {rappel.apercu.seances} séance(s){rappel.apercu.sans_numero > 0 && ` · ${rappel.apercu.sans_numero} patient(s) sans numéro valide`}{rappel.apercu.desinscrits > 0 && ` · ${rappel.apercu.desinscrits} désinscrit(s)`}.</p>}
          <Bouton icone={BellRing} variante="orange" disabled={!rappel.apercu?.a_envoyer || !etat?.configure}
            onClick={() => agir("Envoi des rappels", () => api("/messagerie/rappels", { methode: "POST", corps: { date: rappel.date } }), (r) => `${r.a_envoyer} rappel(s) transmis à WhatsApp`)}>Envoyer les rappels</Bouton>
        </div>
      )}

      {onglet === "auto" && <NotificationsAuto peutRegler={["admin", "super_admin"].includes(utilisateur.role)} />}

      {modal?.type === "contact" && (
        <Modal titre={modal.c ? "Modifier le contact" : "Nouveau contact"} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton variante="principal" disabled={!form.nom || !form.numero} onClick={() => agir("Enregistrement", () => api(modal.c ? `/messagerie/contacts/${modal.c.id}` : "/messagerie/contacts", { methode: modal.c ? "PUT" : "POST", corps: form }), () => "Contact enregistré")}>Enregistrer</Bouton></>}>
          <Texte libelle="Nom" valeur={form.nom} onChange={(v) => setForm({ ...form, nom: v })} placeholder="BADINI Awa" />
          <Texte libelle="Numéro WhatsApp" valeur={form.numero} onChange={(v) => setForm({ ...form, numero: v })} placeholder="+226 70 00 00 00" />
          <Liste libelle="Catégorie" valeur={form.categorie} onChange={(v) => setForm({ ...form, categorie: v })} options={CATEGORIES} vide={null} />
        </Modal>
      )}
      {modal?.type === "modele" && (
        <Modal titre={modal.m ? "Modifier le modèle" : "Nouveau modèle"} onFermer={() => setModal(null)} pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton>
          <Bouton variante="principal" disabled={!form.nom || !form.texte} onClick={() => agir("Enregistrement", () => api(modal.m ? `/messagerie/modeles/${modal.m.id}` : "/messagerie/modeles", { methode: modal.m ? "PUT" : "POST", corps: form }), () => "Modèle enregistré")}>Enregistrer</Bouton></>}>
          <Texte libelle="Nom du modèle" valeur={form.nom} onChange={(v) => setForm({ ...form, nom: v })} />
          <label className="block"><span className="mb-1 block text-xs font-semibold text-ardoise">Texte</span><textarea value={form.texte || ""} onChange={(e) => setForm({ ...form, texte: e.target.value })} rows={5} maxLength={1000} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
        </Modal>
      )}
    </div>
  );
}
