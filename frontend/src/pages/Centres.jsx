// Centres de dialyse (super administrateur) : liste triable, création, modification, activation / désactivation.
// Chaque centre a SES patients, postes, séances, stocks, factures et comptes (modèle e-Kol) ; le préfixe donne les codes patients (CMC-000001).
import { Building2, Pencil, Plus, Power, RefreshCw, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Pastille, Texte } from "../composants/Champs.jsx";
import FicheCentre, { corpsFiche } from "../composants/FicheCentre.jsx";
import Modal from "../composants/Modal.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { trierLignes, useTri } from "../lib/tri.js";

export default function Centres() {
  const { avecToast, toast, rechargerCentres } = useApp();
  const [lignes, setLignes] = useState([]);
  const [modal, setModal] = useState(null);                 // { mode: "creer" | "modifier", centre?, form }
  const [selection, setSelection] = useState(null);
  const tri = useTri();
  const charger = useCallback(async () => { setLignes(await api("/centres")); await rechargerCentres(); }, [rechargerCentres]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);

  const maj = (k, v) => setModal((m) => ({ ...m, form: { ...m.form, [k]: v } }));
  async function enregistrer() {
    const { mode, centre, form } = modal;
    if (mode === "creer") await avecToast("Création du centre", () => api("/centres", { methode: "POST", corps: corpsFiche(form) }), (c) => `Centre « ${c.nom} » créé`);
    else await avecToast("Enregistrement", () => api(`/centres/${centre.id}`, { methode: "PUT", corps: corpsFiche(form) }), () => "Centre modifié");
    setModal(null); await charger();
  }
  // La modification charge la fiche COMPLÈTE (le logo n'est jamais dans la liste).
  async function ouvrirModification(c) {
    try {
      const f = await api(`/centres/${c.id}`);
      setModal({ mode: "modifier", centre: c, form: { nom: f.nom, prefixe: f.prefixe, responsable: f.responsable, titre_responsable: f.titre_responsable, adresse: f.adresse, ville: f.ville,
        telephone: f.telephone, email: f.email, identifiant_fiscal: f.identifiant_fiscal, latitude: f.latitude ?? "", longitude: f.longitude ?? "", logo: f.logo || "" } });
    } catch (e) { toast(e.message, "erreur"); }
  }
  async function basculer(c) {
    await avecToast(c.actif ? "Désactivation" : "Activation", () => api(`/centres/${c.id}`, { methode: "PUT", corps: { actif: !c.actif } }), () => (c.actif ? "Centre désactivé : ses comptes n'ont plus accès" : "Centre activé"));
    await charger();
  }
  const affichees = trierLignes(lignes, tri.cle, tri.sens);
  const valide = modal && modal.form.nom && (modal.mode === "modifier" || /^[A-Za-z0-9]{2,6}$/.test(modal.form.prefixe || ""));
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Centres De Dialyse</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation des centres", charger, () => "Centres actualisés")}>Actualiser</Bouton>
          <Bouton icone={Plus} variante="principal" onClick={() => setModal({ mode: "creer", form: {} })}>Nouveau centre</Bouton>
        </div>
      </div>
      <BandeauVersion detaille className="mb-3" />
      <p className="mb-3 max-w-3xl text-sm text-ardoise">Chaque centre a ses propres patients, postes, séances, stocks, factures et comptes : un centre ne voit jamais les données d'un autre. Après la création, ajoutez l'administrateur du centre dans « Gestion Des Comptes » (choix du centre).</p>
      <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
        <table className="tableau">
          <thead><tr>
            <ThTri cle="nom" tri={tri}>Centre</ThTri><ThTri cle="prefixe" tri={tri}>Préfixe</ThTri><ThTri cle="ville" tri={tri}>Ville</ThTri><ThTri cle="responsable" tri={tri}>Responsable</ThTri>
            <ThTri cle="telephone" tri={tri}>Téléphone</ThTri><ThTri cle="actif" tri={tri}>État</ThTri><ThTri cle="cree_le" tri={tri}>Créé le</ThTri><th>Actions</th>
          </tr></thead>
          <tbody>
            {affichees.map((c) => (
              <tr key={c.id} onClick={() => setSelection(c.id)} className={selection === c.id ? "ligne-selectionnee" : ""}>
                <td className="font-medium text-emeraude"><span className="inline-flex items-center gap-2"><Building2 size={16} />{c.nom}</span></td>
                <td className="font-mono">{c.prefixe}</td><td>{c.ville || "—"}</td><td>{c.responsable || "—"}</td><td>{c.telephone || "—"}</td>
                <td>{c.actif ? <Pastille couleur="vert" icone={Power}>Actif</Pastille> : <Pastille couleur="rouge" icone={Power}>Désactivé</Pastille>}</td>
                <td className="tabular-nums">{(c.cree_le || "").slice(0, 10)}</td>
                <td className="whitespace-nowrap">
                  <BoutonIcone icone={Pencil} libelle="Modifier le centre" onClick={() => ouvrirModification(c)} />
                  <BoutonIcone icone={Power} libelle={c.actif ? "Désactiver le centre" : "Activer le centre"} couleur={c.actif ? "text-rose-600" : "text-emerald-600"} onClick={() => basculer(c)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {modal && (
        <Modal large titre={modal.mode === "creer" ? "Nouveau centre" : `Modifier ${modal.centre.nom}`} onFermer={() => setModal(null)}
          pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton><Bouton icone={Save} variante="principal" disabled={!valide} onClick={enregistrer}>Enregistrer</Bouton></>}>
          <Texte libelle="Nom du centre" valeur={modal.form.nom} onChange={(v) => maj("nom", v)} placeholder="Clinique Philadelphie" />
          <Texte libelle="Préfixe des codes patients" valeur={modal.form.prefixe} onChange={(v) => maj("prefixe", v.toUpperCase())} placeholder="CMC" maxLength={6}
            aide="2 à 6 lettres ou chiffres : les patients seront CMC-000001, CMC-000002… (ne change plus après le premier patient)" />
          <FicheCentre form={modal.form} maj={maj} />
          {modal.mode === "modifier" && <p className="text-xs text-slate-500">« Modifié, non enregistré » : cliquez sur Enregistrer pour valider.</p>}
        </Modal>
      )}
    </div>
  );
}
