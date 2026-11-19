// Gestion des comptes (administration) : liste triable, création, modification (nom, rôle, actif), réinitialisation du mot de passe.
import { KeyRound, Pencil, Plus, RefreshCw, Save, UserCheck, UserX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import ChampMotDePasse from "../composants/ChampMotDePasse.jsx";
import ForceMotDePasse from "../composants/ForceMotDePasse.jsx";
import { Champ, Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { motDePasseAssezFort } from "../lib/motdepasse.js";
import { trierLignes, useTri } from "../lib/tri.js";

export default function Utilisateurs() {
  const { utilisateur, avecToast, toast, centres } = useApp();
  const [lignes, setLignes] = useState([]);
  const [roles, setRoles] = useState([]);
  const [modal, setModal] = useState(null);           // { mode: "creer" | "modifier" | "mdp", compte?, form }
  const [selection, setSelection] = useState(null);
  const tri = useTri();
  const charger = useCallback(async () => { setLignes(await api("/utilisateurs")); setRoles(await api("/roles")); }, []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);

  const maj = (k, v) => setModal((m) => ({ ...m, form: { ...m.form, [k]: v } }));
  async function enregistrer() {
    const { mode, compte, form } = modal;
    if (mode === "creer") await avecToast("Création du compte", () => api("/utilisateurs", { methode: "POST", corps: form }), (c) => `Compte « ${c.login} » créé`);
    else if (mode === "modifier") await avecToast("Enregistrement", () => api(`/utilisateurs/${compte.id}`, { methode: "PUT", corps: { nom_affiche: form.nom_affiche, role: form.role } }), () => "Compte modifié");
    else await avecToast("Réinitialisation", () => api(`/utilisateurs/${compte.id}/reinitialiser`, { methode: "POST", corps: { mot_de_passe: form.mot_de_passe } }), () => "Mot de passe provisoire défini");
    setModal(null); await charger();
  }
  async function basculer(c) {
    await avecToast(c.actif ? "Désactivation" : "Activation", () => api(`/utilisateurs/${c.id}`, { methode: "PUT", corps: { actif: !c.actif } }), () => (c.actif ? "Compte désactivé" : "Compte activé"));
    await charger();
  }
  // Le super administrateur sans centre choisi voit les comptes de tous les centres (colonne « Centre ») et choisit le centre d'un nouveau compte.
  const voitCentre = utilisateur.role === "super_admin";
  const affichees = trierLignes(lignes, tri.cle, tri.sens);
  const valide = modal && (modal.mode === "mdp" ? motDePasseAssezFort(modal.form.mot_de_passe)
    : modal.form.nom_affiche && (modal.mode === "modifier" || (modal.form.login && modal.form.role && motDePasseAssezFort(modal.form.mot_de_passe))));
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
        <h1 className="text-2xl font-semibold">Gestion Des Comptes</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation des comptes", charger, () => "Comptes actualisés")}>Actualiser</Bouton>
          <Bouton icone={Plus} variante="principal" onClick={() => setModal({ mode: "creer", form: { role: "" } })}>Nouveau compte</Bouton>
        </div>
      </div>
      <BandeauVersion detaille className="mb-3" />
      <div className="overflow-x-auto rounded-xl ring-1 ring-encre/10 bg-white">
        <table className="tableau">
          <thead><tr>
            <ThTri cle="login" tri={tri}>Identifiant</ThTri><ThTri cle="nom_affiche" tri={tri}>Nom</ThTri><ThTri cle="role_libelle" tri={tri}>Rôle</ThTri>{voitCentre && <ThTri cle="centre_nom" tri={tri}>Centre</ThTri>}
            <ThTri cle="actif" tri={tri}>État</ThTri><ThTri cle="totp_actif" tri={tri}>2FA</ThTri><th>Actions</th>
          </tr></thead>
          <tbody>
            {affichees.map((c) => (
              <tr key={c.id} onClick={() => setSelection(c.id)} className={selection === c.id ? "ligne-selectionnee" : ""}>
                <td className="font-medium text-emeraude">{c.login}</td><td>{c.nom_affiche}</td><td>{c.role_libelle}</td>{voitCentre && <td>{c.centre_nom || "—"}</td>}
                <td>{c.actif ? <Pastille couleur="vert" icone={UserCheck}>Actif</Pastille> : <Pastille couleur="rouge" icone={UserX}>Désactivé</Pastille>}</td>
                <td>{c.totp_actif ? <Pastille couleur="vert">Oui</Pastille> : <Pastille>Non</Pastille>}</td>
                <td className="whitespace-nowrap">
                  <BoutonIcone icone={Pencil} libelle="Modifier le compte" onClick={() => setModal({ mode: "modifier", compte: c, form: { nom_affiche: c.nom_affiche, role: c.role } })} />
                  <BoutonIcone icone={KeyRound} libelle="Réinitialiser le mot de passe" couleur="text-orange-600" onClick={() => setModal({ mode: "mdp", compte: c, form: {} })} />
                  {c.id !== utilisateur.id && <BoutonIcone icone={c.actif ? UserX : UserCheck} libelle={c.actif ? "Désactiver le compte" : "Activer le compte"} couleur={c.actif ? "text-rose-600" : "text-emerald-600"} onClick={() => basculer(c)} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {modal && (
        <Modal titre={modal.mode === "creer" ? "Nouveau compte" : modal.mode === "mdp" ? `Mot de passe de ${modal.compte.login}` : `Modifier ${modal.compte.login}`} onFermer={() => setModal(null)}
          pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton><Bouton icone={Save} variante="principal" disabled={!valide} onClick={enregistrer}>Enregistrer</Bouton></>}>
          {modal.mode === "creer" && <Texte libelle="Identifiant" valeur={modal.form.login} onChange={(v) => maj("login", v)} placeholder="awa.badini" />}
          {modal.mode !== "mdp" && <Texte libelle="Nom affiché" valeur={modal.form.nom_affiche} onChange={(v) => maj("nom_affiche", v)} placeholder="BADINI Awa" />}
          {modal.mode === "creer" && voitCentre && (
            <Liste libelle="Centre" valeur={modal.form.centre_id ?? (utilisateur.groupe ? "" : utilisateur.centre_id) ?? ""} onChange={(v) => maj("centre_id", v)}
              options={centres.filter((c) => c.actif).map((c) => ({ valeur: c.id, libelle: c.nom }))} vide="— Groupe (aucun centre) —"
              aide="Un compte « Groupe » (super administrateur, directeur général) choisit lui-même son centre de travail." />
          )}
          {modal.mode !== "mdp" && modal.compte?.id !== utilisateur.id && <Liste libelle="Rôle" valeur={modal.form.role} onChange={(v) => maj("role", v)} options={roles} />}
          {modal.mode !== "modifier" && (
            <Champ libelle="Mot de passe provisoire" aide="À changer par la personne à sa première connexion">
              <ChampMotDePasse valeur={modal.form.mot_de_passe || ""} onChange={(v) => maj("mot_de_passe", v)} autoComplete="new-password" />
            </Champ>
          )}
          {modal.mode !== "modifier" && <ForceMotDePasse valeur={modal.form.mot_de_passe} />}
          {modal.mode === "modifier" && <p className="text-xs text-slate-500">« Modifié, non enregistré » : cliquez sur Enregistrer pour valider.</p>}
        </Modal>
      )}
    </div>
  );
}
