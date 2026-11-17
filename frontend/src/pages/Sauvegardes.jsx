// Sauvegardes chiffrées : liste, sauvegarde immédiate, vérification, aperçu puis restauration sûre (confirmation « RESTAURER »),
// copie hors serveur (fichier chiffré), import. Administration : voir / sauvegarder / vérifier ; super administrateur : restaurer, télécharger, importer, supprimer.
import { AlertTriangle, DatabaseBackup, Download, KeyRound, RefreshCw, RotateCcw, ShieldCheck, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api, enregistrerFichier, envoyerBinaire } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateHeureFr, nb } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

const ORIGINE = { auto: ["bleu", "Automatique"], manuelle: ["vert", "Manuelle"], avant_restauration: ["orange", "Avant restauration"], importee: ["violet", "Importée"] };
const taille = (o) => (o > 1048576 ? `${nb(o / 1048576, 1)} Mo` : `${nb(o / 1024, 0)} Ko`);

export default function Sauvegardes() {
  const { utilisateur, avecToast, toast } = useApp();
  const superAdmin = utilisateur.role === "super_admin";
  const [e, setE] = useState(null);
  const [apercu, setApercu] = useState(null);
  const [saisie, setSaisie] = useState("");
  const [selection, setSelection] = useState(null);
  const fichierRef = useRef(null);
  const tri = useTri();
  const charger = useCallback(async () => setE(await api("/admin/sauvegardes")), []);
  useEffect(() => { charger().catch((x) => toast(x.message, "erreur")); }, [charger, toast]);

  async function sauvegarder() { await avecToast("Sauvegarde et vérification", () => api("/admin/sauvegardes", { methode: "POST" }), (f) => `Sauvegarde vérifiée : ${f.total} documents`); await charger(); }
  async function verifier(f) { await avecToast("Vérification de la sauvegarde", () => api(`/admin/sauvegardes/${f.id}/verifier`, { methode: "POST" }), () => "Sauvegarde relue : intacte"); await charger(); }
  async function ouvrirApercu(f) { setSaisie(""); setApercu(await avecToast("Lecture de la sauvegarde", () => api(`/admin/sauvegardes/${f.id}/apercu`), () => "Aperçu prêt")); }
  async function restaurer() {
    const r = await avecToast("Restauration (copie de sécurité d'abord)", () => api(`/admin/sauvegardes/${apercu.sauvegarde.id}/restaurer`, { methode: "POST", corps: { confirmation: saisie } }), (x) => `Restauration terminée : ${x.documents} documents`);
    setApercu(null); await charger(); return r;
  }
  async function supprimer(f) {
    if (!window.confirm("Supprimer définitivement cette sauvegarde ?")) return;
    await avecToast("Suppression", () => api(`/admin/sauvegardes/${f.id}`, { methode: "DELETE" }), () => "Sauvegarde supprimée"); await charger();
  }
  async function importer(ev) {
    const fichier = ev.target.files?.[0]; ev.target.value = "";
    if (!fichier) return;
    await avecToast("Contrôle du fichier", async () => envoyerBinaire("/admin/sauvegardes/importer", await fichier.arrayBuffer()), (f) => `Fichier importé : ${f.total} documents`);
    await charger();
  }
  if (!e) return <div className="p-8 flex justify-center"><span className="jauge" /></div>;
  const lignes = trierLignes(e.sauvegardes, tri.cle, tri.sens, { origine_libelle: (f) => ORIGINE[f.origine]?.[1] });
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
        <h1 className="text-2xl font-semibold">Sauvegardes Chiffrées</h1>
        <div className="flex flex-wrap gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation des sauvegardes", charger, () => "Liste actualisée")}>Actualiser</Bouton>
          {superAdmin && <><input ref={fichierRef} type="file" className="hidden" onChange={importer} />
            <Bouton icone={Upload} variante="neutre" onClick={() => fichierRef.current?.click()}>Importer un fichier</Bouton></>}
          <Bouton icone={DatabaseBackup} variante="principal" disabled={!e.cle_configuree} onClick={sauvegarder}>Sauvegarder maintenant</Bouton>
        </div>
      </div>
      <BandeauVersion detaille className="mb-3" />
      <div className="grid sm:grid-cols-3 gap-3 mb-4">
        <div className={`rounded-xl border p-3 ${e.cle_configuree ? "border-emerald-200 bg-emerald-50" : "border-rose-300 bg-rose-50"}`}>
          <KeyRound size={18} className={e.cle_configuree ? "text-emerald-700" : "text-rose-700"} />
          <div className="font-semibold">{e.cle_configuree ? "Clé de chiffrement configurée" : "Clé de chiffrement ABSENTE"}</div>
          <div className="text-xs text-slate-600">{e.cle_configuree ? "Gardez la variable SAUVEGARDE_CLE en lieu sûr : sans elle, aucune sauvegarde n'est lisible." : "Définissez SAUVEGARDE_CLE (16 caractères minimum) dans Render pour activer les sauvegardes."}</div>
        </div>
        <div className="rounded-xl ring-1 ring-encre/10 bg-white p-3"><ShieldCheck size={18} className="text-turquoise-600" /><div className="font-semibold">Sauvegarde automatique</div>
          <div className="text-xs text-slate-600">Chaque jour vers {e.heure_auto_utc} h (UTC). Dernière vérifiée : {e.derniere_auto ? dateHeureFr(e.derniere_auto) : "aucune"}.</div></div>
        <div className="rounded-xl ring-1 ring-encre/10 bg-white p-3"><DatabaseBackup size={18} className="text-violet-600" /><div className="font-semibold">Conservation</div>
          <div className="text-xs text-slate-600">{e.retention.auto} automatiques, {e.retention.manuelle} manuelles, {e.retention.avant_restauration} copies de sécurité avant restauration.</div></div>
      </div>
      <div className="overflow-x-auto rounded-xl ring-1 ring-encre/10 bg-white">
        <table className="tableau">
          <thead><tr>
            <ThTri cle="cree_le" tri={tri}>Date</ThTri><ThTri cle="origine_libelle" tri={tri}>Origine</ThTri><ThTri cle="par" tri={tri}>Par</ThTri><ThTri cle="taille" tri={tri} numerique>Taille</ThTri>
            <ThTri cle="total" tri={tri} numerique>Documents</ThTri><ThTri cle="verifiee" tri={tri}>Relue</ThTri><ThTri cle="cle_actuelle" tri={tri}>Clé</ThTri><th>Actions</th>
          </tr></thead>
          <tbody>
            {lignes.map((f) => (
              <tr key={f.id} onClick={() => setSelection(f.id)} className={selection === f.id ? "ligne-selectionnee" : ""}>
                <td className="whitespace-nowrap font-medium text-emeraude">{dateHeureFr(f.cree_le)}</td><td><Pastille couleur={ORIGINE[f.origine][0]}>{ORIGINE[f.origine][1]}</Pastille></td><td>{f.par}</td>
                <td className="num">{taille(f.taille)}</td><td className="num">{nb(f.total, 0)}</td>
                <td>{f.verifiee ? <Pastille couleur="vert" icone={ShieldCheck}>Intacte</Pastille> : <Pastille couleur="rouge" icone={AlertTriangle}>À vérifier</Pastille>}</td>
                <td>{f.cle_actuelle ? <Pastille couleur="vert">Clé actuelle</Pastille> : <Pastille couleur="orange" icone={AlertTriangle}>Autre clé</Pastille>}</td>
                <td className="whitespace-nowrap">
                  <BoutonIcone icone={ShieldCheck} libelle="Relire et vérifier cette sauvegarde" onClick={() => verifier(f).catch(() => charger())} />
                  {superAdmin && <>
                    <BoutonIcone icone={RotateCcw} libelle="Aperçu puis restauration" couleur="text-orange-600" onClick={() => ouvrirApercu(f)} />
                    <BoutonIcone icone={Download} libelle="Enregistrer le fichier chiffré (copie hors serveur)" couleur="text-emerald-600" onClick={() => enregistrerFichier(`/admin/sauvegardes/${f.id}/fichier`, `sauvegarde-${f.jour}.dialyse`).catch((x) => toast(x.message, "erreur"))} />
                    <BoutonIcone icone={Trash2} libelle="Supprimer la sauvegarde" couleur="text-rose-600" onClick={() => supprimer(f)} />
                  </>}
                </td>
              </tr>
            ))}
            {!lignes.length && <tr><td colSpan={8} className="text-center text-slate-500 py-6">Aucune sauvegarde. Cliquez sur « Sauvegarder maintenant ».</td></tr>}
          </tbody>
        </table>
      </div>
      {apercu && (
        <Modal titre="Restaurer une sauvegarde" large onFermer={() => setApercu(null)}
          pied={<><Bouton onClick={() => setApercu(null)}>Annuler</Bouton><Bouton icone={RotateCcw} variante="rouge" disabled={saisie.trim() !== apercu.confirmation || !apercu.compte_present} onClick={restaurer}>Restaurer</Bouton></>}>
          <p className="text-sm mb-2">Sauvegarde du <b>{dateHeureFr(apercu.sauvegarde.cree_le)}</b> ({ORIGINE[apercu.sauvegarde.origine][1].toLowerCase()}), relue et intacte.</p>
          <p className="text-sm rounded-lg bg-orange-100 text-orange-900 px-3 py-2 mb-3 flex gap-2"><AlertTriangle size={16} className="mt-0.5 shrink-0" />La restauration REMPLACE les données actuelles. Une copie de sécurité de l'état actuel est créée avant, et remise automatiquement en cas d'échec. Le journal d'audit n'est jamais remplacé.</p>
          {!apercu.compte_present && <p className="text-sm rounded-lg bg-rose-100 text-rose-900 px-3 py-2 mb-3">Votre compte super administrateur n'existe pas dans cette sauvegarde : restauration impossible.</p>}
          {!apercu.cle_actuelle && <p className="text-sm rounded-lg bg-orange-100 text-orange-900 px-3 py-2 mb-3">Cette sauvegarde a été faite avec une autre clé de chiffrement que l'actuelle (elle reste lisible tant que vous disposez de la bonne clé).</p>}
          <table className="tableau mb-3"><thead><tr><th>Données</th><th className="num">Actuel</th><th className="num">Sauvegarde</th><th className="num">Écart</th></tr></thead>
            <tbody>{apercu.lignes.map((l) => <tr key={l.collection} className={l.conservee ? "text-slate-400" : ""}><td>{l.collection}{l.conservee && " (conservé)"}</td><td className="num">{l.actuel}</td><td className="num">{l.sauvegarde}</td>
              <td className={`num font-semibold ${l.conservee ? "" : l.ecart < 0 ? "text-rose-700" : l.ecart > 0 ? "text-emerald-700" : ""}`}>{l.conservee ? "—" : l.ecart > 0 ? "+" + l.ecart : l.ecart}</td></tr>)}</tbody></table>
          <Texte libelle={`Tapez ${apercu.confirmation} pour confirmer`} valeur={saisie} onChange={setSaisie} placeholder={apercu.confirmation} />
        </Modal>
      )}
    </div>
  );
}
