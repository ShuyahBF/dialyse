// Suivi ANONYMISÉ pour le directeur général et les médecins : alertes (critiques d'abord) et patients identifiés par leur seul CODE (âge, sexe, statut).
// Le serveur ne renvoie JAMAIS le nom, le prénom, le téléphone ni l'adresse. Notifications sur le téléphone (application Android) activables ici.
import { AlertTriangle, Bell, BellOff, ClipboardList, RefreshCw, ShieldAlert, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import Bouton from "../composants/Bouton.jsx";
import { Liste, Pastille } from "../composants/Champs.jsx";
import ThTri from "../composants/ThTri.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateFr } from "../lib/format.js";
import { activerNotifications, desactiverNotifications, notificationsActives, notificationsPossibles } from "../lib/pontAndroid.js";
import { trierLignes, useTri } from "../lib/tri.js";

const API = import.meta.env.VITE_API_URL || window.location.origin;
const TYPES = { seance: "Séance", bilan_critique: "Bilan critique", bilan_retard: "Bilan en retard", stock_rupture: "Rupture de stock" };
const FILTRE_GRAVITE = [{ valeur: "toutes", libelle: "Toutes les alertes" }, { valeur: "critique", libelle: "Critiques seulement" }, { valeur: "attention", libelle: "À surveiller seulement" }];
const FILTRE_TYPE = [{ valeur: "tous", libelle: "Tous les types" }, ...Object.entries(TYPES).map(([valeur, libelle]) => ({ valeur, libelle }))];

export default function Suivi() {
  const { toast, avecToast } = useApp();
  const [donnees, setDonnees] = useState(null);
  const [gravite, setGravite] = useState("toutes");
  const [type, setType] = useState("tous");
  const [notif, setNotif] = useState(notificationsActives());
  const tri = useTri();

  const charger = useCallback(() => api("/anonyme").then(setDonnees), []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  // Règle 17 : l'actualisation affiche « … en cours » puis le résultat
  const actualiser = () => avecToast("Actualisation du suivi", charger, () => "Suivi actualisé");

  const alertes = useMemo(() => (donnees?.alertes || []).filter((a) => (gravite === "toutes" || a.gravite === gravite) && (type === "tous" || a.type === type)), [donnees, gravite, type]);
  const patients = useMemo(() => trierLignes(donnees?.patients || [], tri.cle, tri.sens, { alertes: (p) => p.alertes_critiques * 100 + p.alertes_attention }), [donnees, tri.cle, tri.sens]);

  const basculerNotifications = async () => {
    if (notif) { desactiverNotifications(); try { await api("/anonyme/jeton", { methode: "DELETE" }); } catch { /* le jeton local est de toute façon oublié */ } setNotif(false); toast("Notifications arrêtées sur ce téléphone", "ok"); return; }
    await avecToast("Activation des notifications", async () => {
      const { jeton } = await api("/anonyme/jeton", { methode: "POST", corps: { appareil: navigator.userAgent.slice(0, 60) } });
      if (!activerNotifications(API, jeton)) throw new Error("Activation impossible dans cette version de l'application");
      setNotif(true);
    }, () => "Notifications activées : vous serez prévenu des nouvelles alertes");
  };

  if (!donnees) return <p className="text-slate-500">Chargement…</p>;
  const critiques = donnees.alertes.filter((a) => a.gravite === "critique").length, surveiller = donnees.alertes.length - critiques;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-2xl font-semibold">Suivi anonymisé</h1>
          <p className="text-sm text-slate-500">Patients identifiés par leur code seulement : ni nom, ni téléphone, ni adresse.</p></div>
        <Bouton icone={RefreshCw} variante="principal" onClick={actualiser}>Actualiser</Bouton>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-rose-900"><ShieldAlert size={18} className="mb-1" /><div className="text-2xl font-semibold tabular-nums">{critiques}</div><div className="text-sm">Alertes critiques</div></div>
        <div className="rounded-xl border border-orange-200 bg-orange-50 p-3 text-orange-900"><AlertTriangle size={18} className="mb-1" /><div className="text-2xl font-semibold tabular-nums">{surveiller}</div><div className="text-sm">À surveiller</div></div>
        <div className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-emeraude"><Users size={18} className="mb-1" /><div className="text-2xl font-semibold tabular-nums">{donnees.patients.filter((p) => p.statut === "actif").length}</div><div className="text-sm">Patients actifs</div></div>
      </div>

      {notificationsPossibles() && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-white p-4 ring-1 ring-encre/10">
          <Bell size={20} className="text-emeraude" />
          <p className="min-w-0 flex-1 text-sm text-slate-600">Notifications sur ce téléphone : un message à chaque nouvelle alerte (code patient et motif, sans identité).</p>
          <Bouton icone={notif ? BellOff : Bell} variante={notif ? "neutre" : "vert"} onClick={basculerNotifications}>{notif ? "Arrêter les notifications" : "Activer les notifications"}</Bouton>
        </div>
      )}

      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold"><ClipboardList size={18} /> Alertes ({alertes.length})</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Liste libelle="Gravité" valeur={gravite} onChange={setGravite} options={FILTRE_GRAVITE} vide={null} />
          <Liste libelle="Type" valeur={type} onChange={setType} options={FILTRE_TYPE} vide={null} />
        </div>
        <ul className="space-y-2">
          {alertes.length === 0 && <li className="rounded-xl bg-white p-4 text-slate-500 ring-1 ring-encre/10">Aucune alerte pour ces critères.</li>}
          {alertes.map((a) => (
            <li key={a.id} className={`flex flex-wrap items-center gap-2 rounded-xl border p-3 ${a.gravite === "critique" ? "border-rose-200 bg-rose-50" : "border-orange-200 bg-orange-50"}`}>
              <Pastille couleur={a.gravite === "critique" ? "rouge" : "orange"} icone={a.gravite === "critique" ? ShieldAlert : AlertTriangle}>{a.gravite === "critique" ? "Critique" : "À surveiller"}</Pastille>
              {a.code && <span className="rounded bg-white px-2 py-0.5 font-mono text-sm font-semibold text-emeraude ring-1 ring-encre/10">{a.code}</span>}
              <span className="min-w-0 flex-1 text-sm">{a.message}</span>
              <span className="text-xs text-slate-500">{TYPES[a.type]} · {dateFr(a.date)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Users size={18} /> Patients ({patients.length})</h2>
        <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-encre/10">
          <table className="tableau">
            <thead><tr>
              <ThTri cle="code" tri={tri}>Code</ThTri><ThTri cle="age" tri={tri} numerique>Âge</ThTri><ThTri cle="sexe" tri={tri}>Sexe</ThTri>
              <ThTri cle="statut" tri={tri}>Statut</ThTri><ThTri cle="alertes" tri={tri} numerique>Alertes</ThTri><ThTri cle="dernier_bilan" tri={tri}>Dernier bilan</ThTri>
            </tr></thead>
            <tbody>
              {patients.map((p) => (
                <tr key={p.code}>
                  <td className="font-mono font-semibold text-emeraude">{p.code}</td><td className="num">{p.age ?? "—"}</td><td>{p.sexe === "F" ? "Femme" : p.sexe === "M" ? "Homme" : "—"}</td>
                  <td>{p.statut}</td>
                  <td className="num">{p.alertes_critiques > 0 && <Pastille couleur="rouge" icone={ShieldAlert}>{p.alertes_critiques}</Pastille>}{" "}{p.alertes_attention > 0 && <Pastille couleur="orange" icone={AlertTriangle}>{p.alertes_attention}</Pastille>}{!p.alertes_critiques && !p.alertes_attention && "—"}</td>
                  <td>{p.dernier_bilan ? dateFr(p.dernier_bilan) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
