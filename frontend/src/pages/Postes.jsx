// Postes de dialyse : liste triable, création / modification, carnet de maintenance, isolement sérologique.
import { Pencil, Plus, RefreshCw, Save, ShieldAlert, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Case, Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { aujourdhui, dateFr } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

const COULEUR_ETAT = { actif: "vert", maintenance: "orange", hors_service: "rouge" };

export default function Postes() {
  const { utilisateur, avecToast, toast } = useApp();
  const peutEcrire = ["technicien", "admin", "super_admin"].includes(utilisateur.role);
  const [lignes, setLignes] = useState([]);
  const [meta, setMeta] = useState({ types: [], statuts: [] });
  const [modal, setModal] = useState(null);         // { mode: "poste" | "maintenance", poste?, form }
  const [selection, setSelection] = useState(null);
  const tri = useTri();
  const charger = useCallback(async () => { setLignes(await api("/postes")); setMeta(await api("/postes/types-maintenance")); }, []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const maj = (k, v) => setModal((m) => ({ ...m, form: { ...m.form, [k]: v } }));

  async function enregistrer() {
    const { mode, poste, form } = modal;
    if (mode === "maintenance") await avecToast("Enregistrement de l'intervention", () => api(`/postes/${poste.id}/maintenance`, { methode: "POST", corps: form }), () => "Intervention ajoutée au carnet");
    else if (poste) await avecToast("Enregistrement du poste", () => api(`/postes/${poste.id}`, { methode: "PUT", corps: form }), () => "Poste modifié");
    else await avecToast("Création du poste", () => api("/postes", { methode: "POST", corps: form }), () => "Poste créé");
    setModal(null); await charger();
  }
  const affichees = trierLignes(lignes, tri.cle, tri.sens, { maintenance_prochaine: (p) => p.prochaine_maintenance });
  const retard = (p) => p.prochaine_maintenance && p.prochaine_maintenance < aujourdhui();
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
        <h1 className="text-2xl font-semibold">Postes De Dialyse</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation des postes", charger, (v) => "Postes actualisés")}>Actualiser</Bouton>
          {peutEcrire && <Bouton icone={Plus} variante="principal" onClick={() => setModal({ mode: "poste", form: { statut: "actif" } })}>Nouveau poste</Bouton>}
        </div>
      </div>
      <BandeauVersion detaille className="mb-3" />
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="tableau">
          <thead><tr>
            <ThTri cle="nom" tri={tri}>Poste</ThTri><ThTri cle="salle" tri={tri}>Salle</ThTri><ThTri cle="marque" tri={tri}>Machine</ThTri>
            <ThTri cle="statut_libelle" tri={tri}>État</ThTri><ThTri cle="isolement" tri={tri}>Isolement</ThTri>
            <ThTri cle="derniere_maintenance" tri={tri}>Dernière maintenance</ThTri><ThTri cle="maintenance_prochaine" tri={tri}>Prochaine</ThTri>{peutEcrire && <th>Actions</th>}
          </tr></thead>
          <tbody>
            {affichees.map((p) => (
              <tr key={p.id} onClick={() => setSelection(p.id)} className={selection === p.id ? "ligne-selectionnee" : ""}>
                <td className="font-semibold text-sky-800">{p.nom}</td><td>{p.salle}</td><td>{[p.marque, p.modele].filter(Boolean).join(" ")}</td>
                <td><Pastille couleur={COULEUR_ETAT[p.statut]}>{p.statut_libelle}</Pastille></td>
                <td>{p.isolement ? <Pastille couleur="violet" icone={ShieldAlert}>Isolement</Pastille> : <span className="text-slate-400">—</span>}</td>
                <td>{dateFr(p.derniere_maintenance)}</td>
                <td className={retard(p) ? "text-rose-700 font-medium" : ""}>{dateFr(p.prochaine_maintenance)}{retard(p) && " ⚠ en retard"}</td>
                {peutEcrire && (
                  <td className="whitespace-nowrap">
                    <BoutonIcone icone={Pencil} libelle="Modifier le poste" onClick={() => setModal({ mode: "poste", poste: p, form: { nom: p.nom, salle: p.salle || "", marque: p.marque || "", modele: p.modele || "", numero_serie: p.numero_serie || "", statut: p.statut, isolement: !!p.isolement, prochaine_maintenance: p.prochaine_maintenance || "" } })} />
                    <BoutonIcone icone={Wrench} libelle="Ajouter une maintenance" couleur="text-orange-600" onClick={() => setModal({ mode: "maintenance", poste: p, form: { date: aujourdhui(), type: "Préventive" } })} />
                  </td>
                )}
              </tr>
            ))}
            {!affichees.length && <tr><td colSpan={8} className="text-center text-slate-500 py-6">Aucun poste.</td></tr>}
          </tbody>
        </table>
      </div>
      {modal && (
        <Modal titre={modal.mode === "maintenance" ? `Maintenance — ${modal.poste.nom}` : modal.poste ? `Modifier ${modal.poste.nom}` : "Nouveau poste"} onFermer={() => setModal(null)}
          pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton><Bouton icone={Save} variante="principal" disabled={modal.mode === "maintenance" ? !modal.form.date : !modal.form.nom} onClick={enregistrer}>Enregistrer</Bouton></>}>
          {modal.mode === "maintenance" ? (
            <>
              <Texte libelle="Date de l'intervention" type="date" valeur={modal.form.date} onChange={(v) => maj("date", v)} />
              <Liste libelle="Type d'intervention" valeur={modal.form.type} onChange={(v) => maj("type", v)} options={meta.types} />
              <Texte libelle="Remarque" valeur={modal.form.remarque} onChange={(v) => maj("remarque", v)} />
              <Texte libelle="Prochaine maintenance prévue" type="date" valeur={modal.form.prochaine} onChange={(v) => maj("prochaine", v)} />
            </>
          ) : (
            <>
              <Texte libelle="Nom du poste" valeur={modal.form.nom} onChange={(v) => maj("nom", v)} placeholder="Poste 1" />
              <Texte libelle="Salle" valeur={modal.form.salle} onChange={(v) => maj("salle", v)} placeholder="Salle A" />
              <Texte libelle="Marque" valeur={modal.form.marque} onChange={(v) => maj("marque", v)} />
              <Texte libelle="Modèle" valeur={modal.form.modele} onChange={(v) => maj("modele", v)} />
              <Texte libelle="Numéro de série" valeur={modal.form.numero_serie} onChange={(v) => maj("numero_serie", v)} />
              <Liste libelle="État" valeur={modal.form.statut} onChange={(v) => maj("statut", v)} options={meta.statuts} />
              <Case libelle="Poste d'isolement (patients à sérologie VHB / VHC / VIH positive)" valeur={modal.form.isolement} onChange={(v) => maj("isolement", v)} />
              <Texte libelle="Prochaine maintenance" type="date" valeur={modal.form.prochaine_maintenance} onChange={(v) => maj("prochaine_maintenance", v)} />
            </>
          )}
        </Modal>
      )}
    </div>
  );
}
