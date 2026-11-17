// Journal d'audit (administration) : qui a fait quoi, quand. Tableau triable, filtre par action, bouton Actualiser, libellé complet de version.
import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import { Liste } from "../composants/Champs.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateHeureFr } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

export default function Journal() {
  const { avecToast, toast } = useApp();
  const [lignes, setLignes] = useState([]);
  const [action, setAction] = useState("");
  const [selection, setSelection] = useState(null);
  const tri = useTri();
  const charger = useCallback(() => api("/journal" + (action ? `?action=${encodeURIComponent(action)}` : "")).then(setLignes), [action]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const actions = useMemo(() => [...new Set(lignes.map((l) => l.action))].sort(), [lignes]);
  const affichees = trierLignes(lignes, tri.cle, tri.sens);
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
        <h1 className="text-2xl font-semibold">Journal D'audit</h1>
        <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation du journal", charger, () => "Journal actualisé")}>Actualiser</Bouton>
      </div>
      <BandeauVersion detaille className="mb-3" />
      <div className="max-w-xs"><Liste libelle="Filtrer par action" valeur={action} onChange={setAction} options={actions} vide="Toutes les actions" /></div>
      <div className="overflow-x-auto rounded-xl ring-1 ring-encre/10 bg-white">
        <table className="tableau">
          <thead><tr>
            <ThTri cle="quand" tri={tri}>Date et heure</ThTri><ThTri cle="acteur" tri={tri}>Utilisateur</ThTri>
            <ThTri cle="role" tri={tri}>Rôle</ThTri><ThTri cle="action" tri={tri}>Action</ThTri><ThTri cle="detail" tri={tri}>Détail</ThTri>
          </tr></thead>
          <tbody>
            {affichees.map((l, i) => (
              <tr key={i} onClick={() => setSelection(i)} className={selection === i ? "ligne-selectionnee" : ""}>
                <td className="whitespace-nowrap">{dateHeureFr(l.quand)}</td>
                <td className="font-medium text-emeraude">{l.acteur || "—"}</td><td>{l.role}</td>
                <td><span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{l.action}</span></td><td className="text-slate-600">{l.detail}</td>
              </tr>
            ))}
            {!affichees.length && <tr><td colSpan={5} className="text-center text-slate-500 py-6">Aucune ligne.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
