// « Fiche Du Centre » (administrateur) : présentation du centre de travail — responsable, coordonnées, géolocalisation, logo — et papiers à en-tête A4 / A5.
import { FileText, RefreshCw, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import FicheCentre, { corpsFiche } from "../composants/FicheCentre.jsx";
import PdfInterne from "../composants/PdfInterne.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";

const CHAMPS = ["responsable", "titre_responsable", "adresse", "ville", "telephone", "email", "identifiant_fiscal", "latitude", "longitude", "logo"];

export default function FicheCentrePage() {
  const { avecToast, toast } = useApp();
  const [centre, setCentre] = useState(null);       // fiche telle qu'enregistrée
  const [form, setForm] = useState(null);           // fiche en cours de saisie
  const [pdf, setPdf] = useState(null);             // { format } : papier à en-tête affiché dans le lecteur interne
  const charger = useCallback(async () => { const c = await api("/centre"); setCentre(c); setForm(Object.fromEntries(CHAMPS.map((k) => [k, c[k] ?? ""]))); return c; }, []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  if (!form) return <div className="flex justify-center py-10"><span className="jauge" /></div>;

  const modifie = CHAMPS.some((k) => String(form[k] ?? "") !== String(centre[k] ?? ""));
  const maj = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  async function enregistrer() {
    await avecToast("Enregistrement de la fiche", () => api("/centre", { methode: "PUT", corps: corpsFiche(form) }), () => "Fiche du centre enregistrée");
    await charger();
  }
  return (
    <div className="max-w-2xl">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Fiche Du Centre — {centre.nom}</h1>
        <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation de la fiche", charger, () => "Fiche actualisée")}>Actualiser</Bouton>
      </div>
      <BandeauVersion detaille className="mb-3" />
      <div className="rounded-2xl bg-white p-4 ring-1 ring-encre/5">
        <FicheCentre form={form} maj={maj} />
        <div className="flex flex-wrap items-center gap-2">
          <Bouton icone={Save} variante="principal" disabled={!modifie} onClick={enregistrer}>Enregistrer</Bouton>
          {modifie && <span className="text-xs text-orange-700">Modifié, non enregistré</span>}
        </div>
      </div>
      {/* Papiers à en-tête : modèles vierges à imprimer, d'après la fiche ENREGISTRÉE */}
      <div className="mt-4 rounded-2xl bg-white p-4 ring-1 ring-encre/5">
        <h2 className="mb-1 font-semibold">Papiers à en-tête</h2>
        <p className="mb-3 text-sm text-ardoise">Modèles vierges avec le logo, le nom du centre, le responsable, les coordonnées et la position. Enregistrez la fiche avant de les ouvrir.</p>
        <div className="flex flex-wrap gap-2">
          <Bouton icone={FileText} onClick={() => setPdf({ format: "A4" })} disabled={modifie}>Papier à en-tête A4</Bouton>
          <Bouton icone={FileText} onClick={() => setPdf({ format: "A5" })} disabled={modifie}>Papier à en-tête A5</Bouton>
        </div>
      </div>
      {pdf && <PdfInterne titre={`Papier à en-tête ${pdf.format}`} chemin={`/centre/papier-entete?format=${pdf.format}`} onFermer={() => setPdf(null)} />}
    </div>
  );
}
