// Synthèse de TOUS les centres (directeur général et super administrateur du groupe) : une ligne par centre + totaux collés sous le tableau (règle 25).
// Tout est AGRÉGÉ : aucun nom ni code de patient.
import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import { Texte } from "../composants/Champs.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { ajouterJours, aujourdhui, fcfa, nb } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

const COLONNES = [["realisees", "Séances"], ["patients", "Patients traités"], ["patients_actifs", "Patients actifs"], ["absents", "Absents"], ["incidents", "Incidents"],
                  ["taux_absence_pct", "Absence %"], ["facture", "Facturé"], ["encaisse", "Encaissé"]];

export default function SyntheseGroupe() {
  const { avecToast, toast } = useApp();
  const [du, setDu] = useState(aujourdhui().slice(0, 8) + "01");      // du 1er du mois à aujourd'hui
  const [au, setAu] = useState(aujourdhui());
  const [r, setR] = useState(null);
  const tri = useTri();
  const charger = useCallback(async () => { const d = await api(`/groupe/synthese?du=${du}&au=${au}`); setR(d); return d; }, [du, au]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const lignes = r ? trierLignes(r.centres, tri.cle, tri.sens) : [];
  const t = r?.total;
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Synthèse Des Centres</h1>
        <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation de la synthèse", charger, (d) => `Synthèse actualisée : ${d.centres.length} centre(s)`)}>Actualiser</Bouton>
      </div>
      <BandeauVersion className="mb-3" />
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Texte libelle="Du" type="date" valeur={du} onChange={setDu} />
        <Texte libelle="Au" type="date" valeur={au} onChange={setAu} />
        <div className="mb-3 flex gap-2">
          <Bouton petit onClick={() => { setDu(aujourdhui().slice(0, 8) + "01"); setAu(aujourdhui()); }}>Ce mois</Bouton>
          <Bouton petit onClick={() => { setDu(ajouterJours(aujourdhui(), -29)); setAu(aujourdhui()); }}>30 jours</Bouton>
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
        <table className="tableau" data-sans-defilement>
          <thead><tr>
            <ThTri cle="nom" tri={tri}>Centre</ThTri>
            {COLONNES.map(([k, l]) => <ThTri key={k} cle={k} tri={tri} numerique>{l}</ThTri>)}
          </tr></thead>
          <tbody>
            {lignes.map((c) => (
              <tr key={c.id}>
                <td className="font-medium text-emeraude">{c.nom}{!c.actif && <span className="ml-2 text-xs text-rose-700">(désactivé)</span>}</td>
                {COLONNES.map(([k]) => <td key={k} className="num tabular-nums">{k === "facture" || k === "encaisse" ? fcfa(c[k]) : k === "taux_absence_pct" ? nb(c[k]) + " %" : nb(c[k], 0)}</td>)}
              </tr>
            ))}
          </tbody>
          {/* Ligne de TOTAUX toujours visible, nombres à droite (règle 25) ; le taux est recalculé sur les totaux, jamais additionné */}
          {t && (
            <tfoot><tr className="font-semibold">
              <td>Total · {lignes.length} centre(s)</td>
              {COLONNES.map(([k]) => <td key={k} className="num tabular-nums">{k === "facture" || k === "encaisse" ? fcfa(t[k]) : k === "taux_absence_pct" ? nb(t[k]) + " %" : nb(t[k], 0)}</td>)}
            </tr></tfoot>
          )}
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">Chiffres agrégés de la période : aucune identité de patient n'est montrée. « Patients actifs » est l'effectif à ce jour.</p>
    </div>
  );
}
