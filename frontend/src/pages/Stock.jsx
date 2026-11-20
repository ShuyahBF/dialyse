// Consommables et stocks : alertes, articles (triables), entrées / sorties / pertes, lots et ajustements d'inventaire, traçabilité d'un lot.
import { AlertTriangle, ClipboardCheck, List, PackageMinus, PackagePlus, Pencil, Plus, RefreshCw, Save, Search, Siren, Timer } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Bouton, { BoutonIcone } from "../composants/Bouton.jsx";
import { Liste, Pastille, Texte } from "../composants/Champs.jsx";
import Modal from "../composants/Modal.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { aujourdhui, dateFr, dateHeureFr, nb } from "../lib/format.js";
import { trierLignes, useTri } from "../lib/tri.js";

const ETAT = { rupture: ["rouge", "Rupture"], bas: ["orange", "Stock bas"], ok: ["vert", "Disponible"] };
const PER = { perime: ["rouge", "Périmé"], bientot: ["orange", "Bientôt périmé"], ok: ["gris", ""] };
const MOUV = { entree: ["vert", "Entrée"], sortie: ["bleu", "Sortie"], perte: ["rouge", "Perte"], ajustement: ["violet", "Ajustement"] };

export default function Stock() {
  const { utilisateur, avecToast, toast } = useApp();
  const peutEcrire = ["infirmier", "technicien", "admin", "super_admin"].includes(utilisateur.role);
  const peutTracer = ["medecin", "infirmier", "admin", "super_admin"].includes(utilisateur.role);
  const [articles, setArticles] = useState([]);
  const [alertes, setAlertes] = useState(null);
  const [listes, setListes] = useState({ categories: [], unites: [] });
  const [modal, setModal] = useState(null);       // { mode: "article" | "entree" | "sortie" | "ajust", article?, form }
  const [detail, setDetail] = useState(null);      // lots + mouvements d'un article
  const [lotRecherche, setLotRecherche] = useState("");
  const [trace, setTrace] = useState(null);
  const [selection, setSelection] = useState(null);
  const tri = useTri();
  const charger = useCallback(async () => {
    const [a, al, l] = await Promise.all([api("/stock/articles"), api("/stock/alertes"), api("/stock/listes")]);
    setArticles(a); setAlertes(al); setListes(l);
  }, []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  const maj = (k, v) => setModal((m) => ({ ...m, form: { ...m.form, [k]: v } }));

  async function ouvrirLots(a) { setDetail(await api(`/stock/articles/${a.id}/lots`)); }
  async function enregistrer() {
    const { mode, article, form } = modal;
    if (mode === "article") {
      const corps = { nom: form.nom, categorie: form.categorie, unite: form.unite, seuil_alerte: form.seuil_alerte, par_seance: form.par_seance };
      if (article) await avecToast("Enregistrement de l'article", () => api(`/stock/articles/${article.id}`, { methode: "PUT", corps }), () => "Article modifié");
      else await avecToast("Création de l'article", () => api("/stock/articles", { methode: "POST", corps }), (x) => `Article ${x.code} créé`);
    } else if (mode === "entree") await avecToast("Enregistrement de l'entrée", () => api("/stock/entrees", { methode: "POST", corps: { article_id: article.id, ...form, cout_unitaire: form.cout_unitaire === "" ? undefined : Number(form.cout_unitaire) } }), () => "Entrée enregistrée");
    else if (mode === "sortie") await avecToast("Enregistrement de la sortie", () => api("/stock/sorties", { methode: "POST", corps: { article_id: article.id, ...form } }), () => "Sortie enregistrée");
    else await avecToast("Enregistrement de l'ajustement", () => api("/stock/ajustements", { methode: "POST", corps: { article_id: article.id, ...form } }), () => "Inventaire enregistré");
    setModal(null); await charger(); if (detail && article) await ouvrirLots(article);
  }
  async function tracer() {
    const r = await avecToast("Recherche du lot", () => api(`/stock/tracabilite?lot=${encodeURIComponent(lotRecherche.trim())}`), (x) => `${x.length} séance(s) trouvée(s)`);
    setTrace(r);
  }
  const lecteurs = { statut_stock: (a) => a.statut_stock, prochaine_peremption: (a) => a.prochaine_peremption };
  const affiches = trierLignes(articles, tri.cle, tri.sens, lecteurs);
  const valide = modal && (modal.mode === "article" ? modal.form.nom && modal.form.categorie && modal.form.unite
    : modal.mode === "entree" ? modal.form.quantite && modal.form.lot : modal.mode === "sortie" ? modal.form.quantite && (modal.form.type !== "perte" || modal.form.motif)
    : modal.form.lot && modal.form.quantite_constatee !== "" && modal.form.motif);
  const Carte = ({ titre, n, couleur, Ic }) => <div className={`rounded-xl border p-3 ${n ? couleur : "border-slate-200 bg-white text-slate-500"}`}><Ic size={18} className="mb-1" /><div className="text-2xl font-semibold tabular-nums">{n}</div><div className="text-sm">{titre}</div></div>;
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h1 className="text-2xl font-semibold">Consommables Et Stocks</h1>
        <div className="flex gap-2">
          <Bouton icone={RefreshCw} onClick={() => avecToast("Actualisation du stock", charger, () => "Stock actualisé")}>Actualiser</Bouton>
          <Link to="/stock/previsions" className="inline-flex items-center gap-2 rounded-full bg-citron px-5 py-2.5 font-semibold text-white hover:bg-citron-600"><Timer size={18} />Prévisions et commande</Link>
          {peutEcrire && <Bouton icone={Plus} variante="principal" onClick={() => setModal({ mode: "article", form: { seuil_alerte: 0, par_seance: 0 } })}>Nouvel article</Bouton>}
        </div>
      </div>
      {alertes && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <Carte titre="Ruptures" n={alertes.ruptures.length} couleur="border-rose-300 bg-rose-50 text-rose-800" Ic={Siren} />
          <Carte titre="Stock bas" n={alertes.bas.length} couleur="border-orange-300 bg-orange-50 text-orange-800" Ic={AlertTriangle} />
          <Carte titre="Lots périmés en stock" n={alertes.perimes.length} couleur="border-rose-300 bg-rose-50 text-rose-800" Ic={Siren} />
          <Carte titre="Lots bientôt périmés" n={alertes.bientot_perimes.length} couleur="border-orange-300 bg-orange-50 text-orange-800" Ic={AlertTriangle} />
        </div>
      )}
      {peutTracer && (
        <div className="flex flex-wrap items-end gap-2 mb-4 max-w-xl">
          <div className="flex-1 min-w-[12rem]"><Texte libelle="Traçabilité : numéro de lot (rappel de lot)" valeur={lotRecherche} onChange={setLotRecherche} placeholder="LOT-D1" /></div>
          <div className="mb-3"><Bouton icone={Search} variante="orange" disabled={!lotRecherche.trim()} onClick={tracer}>Rechercher le lot</Bouton></div>
        </div>
      )}
      <div className="overflow-x-auto rounded-xl ring-1 ring-encre/10 bg-white">
        <table className="tableau">
          <thead><tr>
            <ThTri cle="code" tri={tri}>Code</ThTri><ThTri cle="nom" tri={tri}>Article</ThTri><ThTri cle="categorie" tri={tri}>Catégorie</ThTri>
            <ThTri cle="stock" tri={tri} numerique>Stock</ThTri><ThTri cle="seuil_alerte" tri={tri} numerique>Seuil</ThTri><ThTri cle="par_seance" tri={tri} numerique>Par séance</ThTri>
            <ThTri cle="prochaine_peremption" tri={tri}>Prochaine péremption</ThTri><ThTri cle="statut_stock" tri={tri}>État</ThTri><th>Actions</th>
          </tr></thead>
          <tbody>
            {affiches.map((a) => (
              <tr key={a.id} onClick={() => setSelection(a.id)} className={`${selection === a.id ? "ligne-selectionnee" : ""} ${a.actif === false ? "opacity-50" : ""}`}>
                <td className="font-semibold text-emeraude">{a.code}</td><td className="font-medium">{a.nom}</td><td className="text-slate-600">{a.categorie}</td>
                <td className={`num font-semibold ${a.statut_stock === "rupture" ? "text-rose-700" : a.statut_stock === "bas" ? "text-orange-700" : "text-emerald-700"}`}>{nb(a.stock, 2)} <span className="text-xs font-normal text-slate-500">{a.unite}</span></td>
                <td className="num">{nb(a.seuil_alerte, 2)}</td><td className="num">{nb(a.par_seance, 2)}</td>
                <td>{dateFr(a.prochaine_peremption)} {PER[a.statut_peremption][1] && <Pastille couleur={PER[a.statut_peremption][0]} icone={AlertTriangle}>{PER[a.statut_peremption][1]}</Pastille>}</td>
                <td><Pastille couleur={ETAT[a.statut_stock][0]}>{ETAT[a.statut_stock][1]}</Pastille></td>
                <td className="whitespace-nowrap">
                  <BoutonIcone icone={List} libelle="Lots et mouvements" onClick={() => ouvrirLots(a)} />
                  {peutEcrire && <>
                    <BoutonIcone icone={PackagePlus} libelle="Entrée de stock" couleur="text-emerald-600" onClick={() => setModal({ mode: "entree", article: a, form: { quantite: "", lot: "", peremption: "", fournisseur: "", cout_unitaire: "", date: aujourdhui() } })} />
                    <BoutonIcone icone={PackageMinus} libelle="Sortie ou perte" couleur="text-rose-600" onClick={() => setModal({ mode: "sortie", article: a, form: { quantite: "", type: "sortie", motif: "", lot: "" } })} />
                    <BoutonIcone icone={Pencil} libelle="Modifier l'article" couleur="text-slate-600" onClick={() => setModal({ mode: "article", article: a, form: { nom: a.nom, categorie: a.categorie, unite: a.unite, seuil_alerte: a.seuil_alerte, par_seance: a.par_seance } })} />
                  </>}
                </td>
              </tr>
            ))}
            {!affiches.length && <tr><td colSpan={9} className="text-center text-slate-500 py-6">Aucun article : créez le catalogue avec « Nouvel article ».</td></tr>}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal titre={modal.mode === "article" ? (modal.article ? `Modifier ${modal.article.nom}` : "Nouvel article") : `${{ entree: "Entrée", sortie: "Sortie ou perte", ajust: "Inventaire" }[modal.mode]} — ${modal.article.nom}`} onFermer={() => setModal(null)}
          pied={<><Bouton onClick={() => setModal(null)}>Annuler</Bouton><Bouton icone={Save} variante="principal" disabled={!valide} onClick={enregistrer}>Enregistrer</Bouton></>}>
          {modal.mode === "article" && <>
            <Texte libelle="Nom de l'article" valeur={modal.form.nom} onChange={(v) => maj("nom", v)} placeholder="Dialyseur FX60" />
            <Liste libelle="Catégorie" valeur={modal.form.categorie} onChange={(v) => maj("categorie", v)} options={listes.categories} />
            <Liste libelle="Unité" valeur={modal.form.unite} onChange={(v) => maj("unite", v)} options={listes.unites} />
            <Texte libelle="Seuil d'alerte (stock bas)" type="number" valeur={modal.form.seuil_alerte} onChange={(v) => maj("seuil_alerte", v)} />
            <Texte libelle="Consommé automatiquement par séance" type="number" step="0.1" valeur={modal.form.par_seance} onChange={(v) => maj("par_seance", v)} aide="0 = non consommé automatiquement. Sinon retiré du stock (lots les plus proches de la péremption) à chaque démarrage de séance." />
          </>}
          {modal.mode === "entree" && <>
            <Texte libelle={`Quantité reçue (${modal.article.unite})`} type="number" step="0.01" valeur={modal.form.quantite} onChange={(v) => maj("quantite", v)} />
            <Texte libelle="Numéro de lot" valeur={modal.form.lot} onChange={(v) => maj("lot", v)} aide="Obligatoire : il permet de retrouver les patients en cas de rappel de lot." />
            <Texte libelle="Date de péremption" type="date" valeur={modal.form.peremption} onChange={(v) => maj("peremption", v)} />
            <Texte libelle="Fournisseur" valeur={modal.form.fournisseur} onChange={(v) => maj("fournisseur", v)} />
            <Texte libelle="Prix unitaire d'achat (FCFA)" type="number" step="1" valeur={modal.form.cout_unitaire} onChange={(v) => maj("cout_unitaire", v)} placeholder="12500" aide="Facultatif. Sert à valoriser les consommables dans la rentabilité ; sans prix, les sorties de ce lot ne sont pas comptées (l'écran Rentabilité le signale). Seule l'administration voit les prix." />
            <Texte libelle="Date de réception" type="date" valeur={modal.form.date} onChange={(v) => maj("date", v)} />
          </>}
          {modal.mode === "sortie" && <>
            <Liste libelle="Type" valeur={modal.form.type} onChange={(v) => maj("type", v)} options={[{ valeur: "sortie", libelle: "Sortie" }, { valeur: "perte", libelle: "Perte (casse, péremption…)" }]} vide="" />
            <Texte libelle={`Quantité (${modal.article.unite})`} type="number" step="0.01" valeur={modal.form.quantite} onChange={(v) => maj("quantite", v)} />
            <Texte libelle="Lot précis (facultatif)" valeur={modal.form.lot} onChange={(v) => maj("lot", v)} aide="Vide : lots les plus proches de la péremption, hors lots périmés. Pour sortir un lot périmé, indiquez son numéro." />
            <Texte libelle={modal.form.type === "perte" ? "Motif (obligatoire)" : "Motif"} valeur={modal.form.motif} onChange={(v) => maj("motif", v)} />
          </>}
          {modal.mode === "ajust" && <>
            <Texte libelle="Numéro de lot compté" valeur={modal.form.lot} onChange={(v) => maj("lot", v)} />
            <Texte libelle="Quantité constatée" type="number" step="0.01" valeur={modal.form.quantite_constatee} onChange={(v) => maj("quantite_constatee", v)} />
            <Texte libelle="Motif de l'écart" valeur={modal.form.motif} onChange={(v) => maj("motif", v)} placeholder="Inventaire de novembre" />
          </>}
        </Modal>
      )}
      {detail && (
        <Modal titre={`${detail.article.nom} — lots et mouvements`} large onFermer={() => setDetail(null)} pied={<>
          {peutEcrire && <Bouton icone={ClipboardCheck} variante="orange" onClick={() => setModal({ mode: "ajust", article: detail.article, form: { lot: "", quantite_constatee: "", motif: "" } })}>Inventaire d'un lot</Bouton>}
          <Bouton onClick={() => setDetail(null)}>Fermer</Bouton></>}>
          <table className="tableau mb-4"><thead><tr><th>Lot</th><th>Péremption</th><th className="num">Restant</th>{detail.lots.some((l) => "cout_unitaire" in l) && <th className="num">Prix unitaire</th>}<th>État</th></tr></thead>
            <tbody>{detail.lots.map((l) => <tr key={l.id}><td className="font-medium text-emeraude">{l.numero}</td><td>{dateFr(l.peremption)}</td><td className="num">{nb(l.quantite_restante, 2)}</td>
              {detail.lots.some((x) => "cout_unitaire" in x) && <td className="num tabular-nums">{l.cout_unitaire == null ? <span className="font-semibold text-orange-700" title="Prix inconnu : les sorties de ce lot ne sont pas valorisées">à renseigner</span> : `${nb(l.cout_unitaire, 0)} F`}</td>}
              <td>{PER[l.statut_peremption][1] ? <Pastille couleur={PER[l.statut_peremption][0]} icone={AlertTriangle}>{PER[l.statut_peremption][1]}</Pastille> : <span className="text-slate-400">—</span>}</td></tr>)}
              {!detail.lots.length && <tr><td colSpan={5} className="text-slate-500">Aucun lot.</td></tr>}</tbody></table>
          <h3 className="font-semibold mb-2">Derniers mouvements</h3>
          <table className="tableau"><thead><tr><th>Date</th><th>Type</th><th className="num">Quantité</th><th>Lot</th><th>Motif</th><th>Par</th></tr></thead>
            <tbody>{detail.mouvements.map((m) => <tr key={m.id}><td className="whitespace-nowrap">{dateHeureFr(m.quand)}</td><td><Pastille couleur={MOUV[m.type][0]}>{MOUV[m.type][1]}</Pastille></td>
              <td className={`num ${m.delta < 0 ? "text-rose-700" : "text-emerald-700"}`}>{m.delta > 0 ? "+" : ""}{nb(m.delta, 2)}</td><td>{(m.lots || []).map((l) => l.numero).join(", ")}</td><td>{m.motif}</td><td>{m.par}</td></tr>)}</tbody></table>
        </Modal>
      )}
      {trace && (
        <Modal titre={`Traçabilité du lot ${lotRecherche.trim()}`} large onFermer={() => setTrace(null)} pied={<Bouton onClick={() => setTrace(null)}>Fermer</Bouton>}>
          {!trace.length ? <p className="text-sm text-slate-500">Ce lot n'a été utilisé dans aucune séance.</p> : (
            <><p className="text-sm text-slate-600 mb-2">{trace.length} séance(s) : à contacter en cas de rappel de lot.</p>
              <table className="tableau"><thead><tr><th>Date</th><th>Créneau</th><th>Patient</th><th>Code</th><th>Téléphone</th><th>Poste</th></tr></thead>
                <tbody>{trace.map((t, i) => <tr key={i}><td>{dateFr(t.date)}</td><td className="capitalize">{t.creneau}</td><td className="font-medium">{t.patient}</td><td className="text-emeraude">{t.code}</td><td>{t.telephone}</td><td>{t.poste}</td></tr>)}</tbody></table></>
          )}
        </Modal>
      )}
    </div>
  );
}
