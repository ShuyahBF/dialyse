// Modèles de dossier d'adhésion à la file active : le modèle par défaut (liste nationale des pièces) + les VARIANTES ou modèles propres de chaque centre.
// Administration seulement. Chaque patient est rattaché à un modèle (onglet « Pièces du dossier » de sa fiche). Détails d'un modèle en fenêtre modale (règle 20).
import { ArrowDown, ArrowUp, Copy, FilePlus2, Pencil, Plus, RefreshCw, Save, Star, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Case, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";

/** Éditeur d'un modèle : nom, centre, liste de pièces (libellé, obligatoire, ordre). Bouton Enregistrer actif seulement si le modèle a changé (règle 15). */
function Editeur({ modele, onFermer, onEnregistre }) {
  const { avecToast } = useApp();
  const depart = { nom: modele.nom || "", centre: modele.centre || "", pieces: (modele.pieces || []).map((p) => ({ ...p })) };
  const [v, setV] = useState(depart);
  const modifie = JSON.stringify(v) !== JSON.stringify(depart) || !modele.id;
  const piece = (i, champ, x) => setV((s) => ({ ...s, pieces: s.pieces.map((p, j) => (j === i ? { ...p, [champ]: x } : p)) }));
  const deplacer = (i, d) => setV((s) => { const a = [...s.pieces]; const j = i + d; if (j < 0 || j >= a.length) return s; [a[i], a[j]] = [a[j], a[i]]; return { ...s, pieces: a }; });
  const valide = v.nom.trim().length >= 3 && v.pieces.length > 0 && v.pieces.every((p) => p.libelle.trim().length >= 3) && v.pieces.some((p) => p.obligatoire);
  const enregistrer = async () => {
    const corps = { nom: v.nom, centre: v.centre, pieces: v.pieces };
    const r = await avecToast("Enregistrement du modèle", () => modele.id ? api(`/modeles-adhesion/${modele.id}`, { methode: "PUT", corps }) : api("/modeles-adhesion", { methode: "POST", corps }), () => "Modèle enregistré");
    onEnregistre(r);
  };
  return (
    <Modal titre={modele.id ? "Modifier le modèle" : "Nouveau modèle"} large onFermer={onFermer}
      pied={<><span className={`mr-auto self-center text-xs ${modifie ? "text-orange-700 font-medium" : "text-slate-400"}`}>{modifie ? "Modifié, non enregistré" : "Aucune modification"}</span>
        <Bouton onClick={onFermer}>Fermer</Bouton><Bouton icone={Save} variante="principal" disabled={!modifie || !valide} onClick={enregistrer}>Enregistrer</Bouton></>}>
      <Texte libelle="Nom du modèle" valeur={v.nom} onChange={(x) => setV({ ...v, nom: x })} placeholder="Centre de dialyse de Bobo-Dioulasso" />
      <Texte libelle="Centre concerné (facultatif)" valeur={v.centre} onChange={(x) => setV({ ...v, centre: x })} placeholder="Laisser vide pour un modèle commun" />
      <p className="text-sm font-medium mt-2 mb-1">Pièces à fournir ({v.pieces.length})</p>
      <ul className="space-y-2">
        {v.pieces.map((p, i) => (
          <li key={p.cle || i} className="rounded-xl bg-brume p-2 ring-1 ring-encre/5">
            <textarea value={p.libelle} rows={2} onChange={(e) => piece(i, "libelle", e.target.value)} aria-label={`Libellé de la pièce ${i + 1}`}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white" placeholder="Intitulé de la pièce et précisions" />
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={p.obligatoire} onChange={(e) => piece(i, "obligatoire", e.target.checked)} className="h-4 w-4 accent-emeraude" /> Obligatoire</label>
              <span className="ml-auto flex">
                <BoutonIcone icone={ArrowUp} libelle="Monter" onClick={() => deplacer(i, -1)} /><BoutonIcone icone={ArrowDown} libelle="Descendre" onClick={() => deplacer(i, 1)} />
                <BoutonIcone icone={Trash2} libelle="Retirer cette pièce" couleur="text-rose-600" onClick={() => setV((s) => ({ ...s, pieces: s.pieces.filter((_, j) => j !== i) }))} />
              </span>
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-2"><Bouton icone={Plus} petit onClick={() => setV((s) => ({ ...s, pieces: [...s.pieces, { libelle: "", obligatoire: true }] }))}>Ajouter une pièce</Bouton></div>
      {!v.pieces.some((p) => p.obligatoire) && <p className="mt-2 text-xs text-rose-700">Au moins une pièce doit être obligatoire.</p>}
    </Modal>
  );
}

export default function ModelesAdhesion() {
  const { toast, avecToast } = useApp();
  const [modeles, setModeles] = useState(null);
  const [edition, setEdition] = useState(null);
  const charger = useCallback(() => api("/modeles-adhesion").then((r) => setModeles(r.modeles)), []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const action = (enCours, fn, ok) => avecToast(enCours, fn, () => ok).then(charger).catch(() => {});
  if (!modeles) return <p className="text-slate-500">Chargement…</p>;
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <h1 className="text-2xl font-semibold">Modèles de dossier d'adhésion</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation des modèles", charger, () => "Modèles actualisés")}>Actualiser</Bouton>
          <Bouton icone={FilePlus2} variante="principal" onClick={() => setEdition({ nom: "", centre: "", pieces: [{ libelle: "", obligatoire: true }] })}>Nouveau modèle</Bouton>
        </div>
      </div>
      <p className="text-sm text-slate-600 mb-3">Liste des pièces à fournir pour entrer dans la file active d'un centre de dialyse. Le modèle par défaut s'applique aux patients qui n'en ont pas choisi ;
        chaque centre peut avoir sa variante ou son modèle propre. On note la réception de chaque pièce, jamais son contenu.</p>
      <div className="grid gap-3 md:grid-cols-2">
        {modeles.map((m) => (
          <section key={m.id} className="rounded-2xl bg-white p-4 ring-1 ring-encre/10">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold">{m.nom}</h2>
              {m.par_defaut && <Pastille couleur="vert" icone={Star}>Par défaut</Pastille>}
              {m.centre && <Pastille couleur="bleu">{m.centre}</Pastille>}
            </div>
            <p className="text-xs text-slate-500 mt-1">{m.pieces.length} pièce(s), dont {m.pieces.filter((p) => p.obligatoire).length} obligatoire(s) · {m.patients} patient(s)</p>
            <ul className="mt-2 list-disc pl-5 text-sm space-y-0.5">{m.pieces.map((p) => <li key={p.cle}>{p.libelle}{!p.obligatoire && <span className="text-slate-500"> (facultatif)</span>}</li>)}</ul>
            <div className="mt-3 flex flex-wrap gap-2">
              <Bouton icone={Pencil} petit onClick={() => setEdition(m)}>Modifier</Bouton>
              <Bouton icone={Copy} petit onClick={() => setEdition({ nom: `${m.nom} (variante)`, centre: "", pieces: m.pieces.map((p) => ({ libelle: p.libelle, obligatoire: p.obligatoire })) })}>Dupliquer</Bouton>
              {!m.par_defaut && <Bouton icone={Star} petit variante="orange" onClick={() => action("Changement du modèle par défaut", () => api(`/modeles-adhesion/${m.id}/defaut`, { methode: "POST" }), "Modèle par défaut changé")}>Par défaut</Bouton>}
              {!m.par_defaut && <Bouton icone={Trash2} petit variante="rouge" onClick={() => window.confirm(`Supprimer le modèle « ${m.nom} » ?`) && action("Suppression du modèle", () => api(`/modeles-adhesion/${m.id}`, { methode: "DELETE" }), "Modèle supprimé")}>Supprimer</Bouton>}
            </div>
          </section>
        ))}
      </div>
      {edition && <Editeur modele={edition} onFermer={() => setEdition(null)} onEnregistre={() => { setEdition(null); charger(); }} />}
    </div>
  );
}
