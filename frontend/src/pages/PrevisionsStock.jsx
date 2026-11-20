// Prévisions de stock et bon de commande : quand chaque consommable va-t-il manquer, et que commander pour tenir 15, 30, 60 ou 90 jours ?
// Calcul fait par le SERVEUR (consommation passée + séances planifiées, lots périmés écartés) ; les prix et coûts ne sont vus que de l'administration.
// Une prévision AIDE à commander : elle ne commande rien toute seule. Règles : colonnes triables, nombres à droite, totaux collés sous le tableau (règle 25), toast à l'actualisation.
import { AlertTriangle, ArrowLeft, FileText, PackageX, RefreshCw, ShoppingCart, Timer } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import { Liste, Pastille } from "../composants/Champs.jsx";
import PdfInterne from "../composants/PdfInterne.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateFr, fcfa, nb } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

const ETAT = { rupture: ["rouge", "Rupture"], urgent: ["orange", "Urgent"], a_commander: ["bleu", "À commander"], ok: ["vert", "Suffisant"] };

export default function PrevisionsStock() {
  const { utilisateur, avecToast, toast } = useApp();
  const peutCommander = ["infirmier", "technicien", "admin", "super_admin"].includes(utilisateur.role);
  const [couverture, setCouverture] = useState(30);
  const [res, setRes] = useState(null);
  const [pdf, setPdf] = useState(false);
  const [seulementACommander, setSeulementACommander] = useState(false);
  const tri = useTri();
  const charger = useCallback(async (c = couverture) => { const r = await api(`/stock/previsions?couverture=${c}`); setRes(r); return r; }, [couverture]);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  if (!res) return <div className="flex justify-center py-10"><span className="jauge" /></div>;

  const prix = res.prix_visibles;
  const affichees = trierLignes(res.lignes.filter((l) => !seulementACommander || l.a_commander > 0), tri.cle, tri.sens);
  const coutAffiche = affichees.reduce((s, l) => s + (l.cout_estime || 0), 0);
  const t = res.totaux;
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><Timer size={24} className="text-citron" /> Prévisions Et Commande</h1>
        <div className="flex flex-wrap gap-2">
          <Link to="/stock" className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 font-semibold text-encre ring-1 ring-encre/15 hover:ring-encre/40"><ArrowLeft size={18} />Retour au stock</Link>
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation des prévisions", charger, (r) => `${r.lignes.length} article(s) relus : ${r.totaux.a_commander} à commander`)}>Actualiser</Bouton>
          {peutCommander && <Bouton icone={FileText} variante="orange" onClick={() => setPdf(true)} disabled={t.a_commander === 0}>Bon de commande</Bouton>}
        </div>
      </div>
      <BandeauVersion className="mb-3" />
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Liste libelle="Couvrir" valeur={String(couverture)} onChange={(v) => setCouverture(Number(v))} options={res.couvertures.map((c) => ({ valeur: String(c), libelle: `${c} jours` }))} vide="" />
        <label className="mb-3 flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-emeraude" checked={seulementACommander} onChange={(e) => setSeulementACommander(e.target.checked)} />Seulement ce qui est à commander</label>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {[["Ruptures", t.en_rupture, "text-rose-700", PackageX], ["Urgents (moins de 7 jours)", t.urgents, "text-orange-700", AlertTriangle], ["Articles à commander", t.a_commander, "text-emeraude", ShoppingCart],
          ...(prix ? [["Coût estimé de la commande", fcfa(t.cout_estime), "text-encre", FileText]] : [])].map(([l, v, c, Ic]) => (
          <div key={l} className="rounded-2xl bg-white p-3 ring-1 ring-encre/5"><p className="flex items-center gap-1.5 text-xs text-ardoise"><Ic size={14} aria-hidden="true" />{l}</p><p className={`text-lg font-bold tabular-nums ${c}`}>{v}</p></div>))}
      </div>
      {prix && t.sans_prix > 0 && (
        <p className="mb-3 flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-900" data-testid="alerte-sans-prix">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span><b>{t.sans_prix} article(s)</b> à commander n'ont pas de prix connu : leur coût n'est pas compté. Renseignez le prix unitaire à la prochaine réception.</span>
        </p>
      )}

      <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
        <table className="tableau">
          <thead><tr>
            <ThTri cle="statut_libelle" tri={tri}>État</ThTri><ThTri cle="code" tri={tri}>Code</ThTri><ThTri cle="nom" tri={tri}>Article</ThTri>
            <ThTri cle="stock" tri={tri} numerique>Stock utilisable</ThTri><ThTri cle="conso_jour" tri={tri} numerique>Conso. / jour</ThTri><ThTri cle="jours_restants" tri={tri} numerique>Jours restants</ThTri>
            <ThTri cle="rupture_estimee" tri={tri}>Rupture estimée</ThTri><ThTri cle="a_commander" tri={tri} numerique>À commander</ThTri>
            {prix && <><ThTri cle="prix_unitaire" tri={tri} numerique>Prix unitaire</ThTri><ThTri cle="cout_estime" tri={tri} numerique>Coût estimé</ThTri></>}
          </tr></thead>
          <tbody>
            {affichees.map((l) => (
              <tr key={l.article_id}>
                <td><Pastille couleur={ETAT[l.statut][0]} icone={l.statut === "rupture" || l.statut === "urgent" ? AlertTriangle : undefined}>{ETAT[l.statut][1]}</Pastille></td>
                <td className="font-semibold text-emeraude">{l.code}</td>
                <td className="font-medium">{l.nom}{l.stock_perime > 0 && <span className="ml-1 text-xs font-semibold text-rose-700" title="Lots périmés écartés du stock utilisable">({nb(l.stock_perime, 2)} périmé(s))</span>}</td>
                <td className="num tabular-nums">{nb(l.stock, 2)} <span className="text-xs text-slate-500">{l.unite}</span></td>
                <td className="num tabular-nums">{l.conso_jour ? nb(l.conso_jour, 2) : "—"}</td>
                <td className={`num tabular-nums ${l.statut === "urgent" ? "font-semibold text-orange-700" : ""}`}>{l.jours_restants === null ? "—" : nb(l.jours_restants, 0)}</td>
                <td className="tabular-nums">{l.rupture_estimee ? dateFr(l.rupture_estimee) : "—"}</td>
                <td className={`num tabular-nums font-semibold ${l.a_commander > 0 ? "text-emeraude" : "text-slate-400"}`}>{l.a_commander}</td>
                {prix && <><td className="num tabular-nums">{l.prix_unitaire === null ? <span className="text-xs font-semibold text-orange-700">à renseigner</span> : fcfa(l.prix_unitaire)}</td>
                  <td className="num tabular-nums">{l.cout_estime === null ? "—" : fcfa(l.cout_estime)}</td></>}
              </tr>
            ))}
            {affichees.length === 0 && <tr><td colSpan={prix ? 10 : 8} className="py-6 text-center text-slate-500">Aucun article à afficher.</td></tr>}
          </tbody>
          {/* Totaux collés sous le tableau (règle 25) : nombre de lignes et coût ; les quantités ne s'additionnent pas (unités différentes) */}
          <tfoot><tr className="font-semibold"><td colSpan={3}>Total · {affichees.length} article(s)</td><td colSpan={5} />{prix && <><td /><td className="num tabular-nums">{fcfa(coutAffiche)}</td></>}</tr></tfoot>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">Besoin = séances planifiées sur la période × quantité par séance (articles « par séance »), sinon consommation des 30 derniers jours × durée. À commander = besoin + seuil d'alerte (stock de sécurité) − stock utilisable (lots non périmés).
        Une prévision aide à commander, elle ne commande rien toute seule.{prix ? " Prix = dernier lot reçu avec un prix." : " Les prix ne sont vus que de l'administration."}</p>
      {pdf && <PdfInterne titre="Bon de commande" chemin={`/stock/bon-commande?couverture=${couverture}`} onFermer={() => setPdf(false)} />}
    </div>
  );
}
