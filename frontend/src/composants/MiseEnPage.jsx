// Cadre du portail (présentation ZandGo) : barre latérale bleu nuit de 230 px (logo, menus à pictogrammes, élément actif en orange,
// nom + rôle en pastille, déconnexion, version), menu replié derrière un bouton « Menu » sur téléphone. Majuscule à chaque mot (règle 18).
import { Activity, Building2, Droplets, TrendingUp, Users as UsersEquipe, Wrench, BarChart3, CalendarDays, CalendarRange, ClipboardList, MessageCircle, DatabaseBackup, ClipboardCheck, LayoutDashboard, LogOut, ShieldAlert, Menu, Monitor, Package, Receipt, ShieldCheck, UserCog, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useApp } from "../lib/contexte.jsx";
import { titreMenu } from "../lib/format.js";
import BandeauVersion from "./BandeauVersion.jsx";
import Logo from "./Logo.jsx";
import ProtectionEcran from "./ProtectionEcran.jsx";

// Chaque entrée : chemin, libellé, pictogramme, rôles autorisés (liste vide = tous).
const MENU = [
  { chemin: "/", libelle: "tableau de bord", icone: LayoutDashboard, roles: ["super_admin", "admin", "direction", "medecin", "infirmier"] },
  { chemin: "/suivi", libelle: "suivi anonymisé", icone: ShieldAlert, roles: ["super_admin", "admin", "direction", "medecin"] },
  { chemin: "/groupe", libelle: "synthèse des centres", icone: BarChart3, roles: ["super_admin", "direction"], groupe: true },
  { chemin: "/rapports", libelle: "rapports", icone: BarChart3, roles: ["super_admin", "admin", "direction", "medecin", "infirmier"] },
  { chemin: "/aujourdhui", libelle: "aujourd'hui", icone: Activity, roles: ["super_admin", "admin", "medecin", "infirmier", "secretariat"] },
  { chemin: "/calendrier", libelle: "calendrier d'activité", icone: CalendarRange, roles: ["super_admin", "admin", "medecin", "infirmier", "secretariat"] },
  { chemin: "/reservations", libelle: "réservations", icone: ClipboardCheck, roles: ["super_admin", "admin", "medecin", "infirmier", "secretariat"] },
  { chemin: "/messagerie", libelle: "centre de messagerie WA", icone: MessageCircle, roles: ["super_admin", "admin", "secretariat"] },
  { chemin: "/planning", libelle: "planning des séances", icone: CalendarDays, roles: ["super_admin", "admin", "medecin", "infirmier", "secretariat"] },
  { chemin: "/patients", libelle: "patients", icone: Users, roles: ["super_admin", "admin", "medecin", "infirmier", "secretariat"] },
  { chemin: "/modeles", libelle: "modèles de dossier d'adhésion", icone: ClipboardCheck, roles: ["super_admin", "admin"] },
  { chemin: "/personnel", libelle: "planning du personnel", icone: UsersEquipe, roles: ["super_admin", "admin", "medecin", "infirmier", "secretariat", "direction", "technicien"] },
  { chemin: "/maintenance", libelle: "maintenance des postes", icone: Wrench, roles: ["super_admin", "admin", "technicien", "medecin", "infirmier", "secretariat", "direction"] },
  { chemin: "/eau", libelle: "contrôle de l'eau", icone: Droplets, roles: ["super_admin", "admin", "technicien", "medecin", "infirmier"] },
  { chemin: "/rentabilite", libelle: "rentabilité", icone: TrendingUp, roles: ["super_admin", "admin", "direction"] },
  { chemin: "/postes", libelle: "postes de dialyse", icone: Monitor, roles: [] },
  { chemin: "/stock", libelle: "consommables et stocks", icone: Package, roles: ["super_admin", "admin", "medecin", "infirmier", "technicien"] },
  { chemin: "/facturation", libelle: "facturation", icone: Receipt, roles: ["super_admin", "admin", "secretariat"] },
  { chemin: "/centres", libelle: "centres de dialyse", icone: Building2, roles: ["super_admin"] },
  { chemin: "/fiche-centre", libelle: "fiche du centre", icone: Building2, roles: ["super_admin", "admin"] },
  { chemin: "/utilisateurs", libelle: "gestion des comptes", icone: UserCog, roles: ["super_admin", "admin"] },
  { chemin: "/journal", libelle: "journal d'audit", icone: ClipboardList, roles: ["super_admin", "admin"] },
  { chemin: "/sauvegardes", libelle: "sauvegardes chiffrées", icone: DatabaseBackup, roles: ["super_admin", "admin"] },
  { chemin: "/compte", libelle: "mon compte", icone: ShieldCheck, roles: [] },
];

export default function MiseEnPage() {
  const { utilisateur, deconnecter, centres, centreChoisi, choisirCentre, compteurs } = useApp();
  const { pathname } = useLocation();
  const [ouvert, setOuvert] = useState(false);            // menu replié sur téléphone, refermé après chaque choix
  useEffect(() => setOuvert(false), [pathname]);
  const entrees = MENU.filter((m) => (m.roles.length === 0 || m.roles.includes(utilisateur.role)) && (!m.groupe || utilisateur.groupe));
  // Compte du groupe (super administrateur, direction) sans centre choisi : seules les pages « Centres », « Comptes » et « Mon compte » fonctionnent.
  const sansCentre = utilisateur.groupe && !centreChoisi;
  const pageLibre = ["/groupe", "/centres", "/fiche-centre", "/utilisateurs", "/sauvegardes", "/compte"].some((p) => pathname.startsWith(p));
  const nomCentre = utilisateur.groupe ? (centres.find((c) => c.id === centreChoisi)?.nom || "") : utilisateur.centre_nom;
  // Logo du centre de travail (barre du haut)
  const [logoCentre, setLogoCentre] = useState("");
  useEffect(() => {
    if (!nomCentre) { setLogoCentre(""); return; }
    api("/centre").then((c) => setLogoCentre(c.logo || "")).catch(() => setLogoCentre(""));
  }, [nomCentre, centreChoisi]);
  return (
    <ProtectionEcran>
      {/* BARRE DU HAUT : le centre de travail, tout en haut de chaque écran (liste déroulante pour un compte du groupe, nom imposé pour les autres) */}
      <header className="sticky top-0 z-50 flex h-12 items-center gap-3 bg-white px-4 shadow-sm ring-1 ring-encre/10" data-testid="barre-centre">
        {logoCentre ? <img src={logoCentre} alt="" className="h-8 w-auto max-w-[96px] object-contain" /> : <Building2 size={20} className="text-citron" aria-hidden="true" />}
        <span className="hidden text-[11px] font-semibold uppercase tracking-wider text-ardoise sm:inline">Centre</span>
        {utilisateur.groupe ? (
          <select value={centreChoisi} onChange={(e) => choisirCentre(e.target.value)} aria-label="Centre de travail" data-testid="selecteur-centre"
            className="min-w-0 max-w-[60vw] rounded-lg border border-encre/15 bg-brume px-3 py-1.5 text-sm font-semibold text-encre focus:outline-none focus:ring-2 focus:ring-citron">
            <option value="">— Choisir un centre —</option>
            {centres.filter((c) => c.actif).map((c) => <option key={c.id} value={c.id}>{c.nom}</option>)}
          </select>
        ) : <span className="truncate text-sm font-semibold text-encre" data-testid="nom-centre">{nomCentre}</span>}
        {utilisateur.groupe && !centreChoisi && <span className="hidden text-xs font-semibold text-orange-700 sm:inline">Choisissez le centre où vous travaillez</span>}
      </header>
      <div className="min-h-[calc(100vh-3rem)] overflow-x-clip md:grid md:grid-cols-[230px_1fr]">
        <aside className="barre-laterale sticky top-12 z-40 flex max-h-[calc(100vh-3rem)] flex-col gap-1 overflow-y-auto bg-encre p-4 text-white md:h-[calc(100vh-3rem)] md:overscroll-contain">
          <div className="flex items-center justify-between px-2 md:mb-4">
            <Logo clair />
            <button type="button" onClick={() => setOuvert((o) => !o)} aria-expanded={ouvert} aria-controls="menu-portail"
              className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-white ring-1 ring-white/20 md:hidden">
              {ouvert ? <X size={18} /> : <Menu size={18} />}{ouvert ? "Fermer" : "Menu"}
            </button>
          </div>
          <nav id="menu-portail" className={`${ouvert ? "flex" : "hidden"} mt-3 flex-col gap-1 md:mt-0 md:flex`}>
            {entrees.map(({ chemin, libelle, icone: Icone }) => (
              <NavLink key={chemin} to={chemin} end={chemin === "/"}
                className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-1.5 text-sm font-semibold ${isActive ? "bg-white/10 text-citron" : "text-white/80 hover:bg-white/5 hover:text-white"}`}>
                <Icone size={18} className="shrink-0" /> <span className="min-w-0 flex-1">{titreMenu(libelle)}</span>
                {/* Pastille : nombre d'éléments non traités de ce lien (règle du menu, 19/11/2026) ; jamais la couleur seule : le nombre est écrit */}
                {compteurs[chemin] > 0 && <span className="shrink-0 rounded-full bg-citron px-1.5 py-0.5 text-[11px] font-bold leading-none text-white" aria-label={`${compteurs[chemin]} non traité(s)`} data-testid={`pastille-${chemin.slice(1)}`}>{compteurs[chemin] > 99 ? "99+" : compteurs[chemin]}</span>}
              </NavLink>
            ))}
          </nav>
          <div className={`${ouvert ? "block" : "hidden"} mt-auto space-y-2 px-2 pt-6 text-xs text-white/60 md:block`}>
            <p className="truncate font-semibold text-white/85">{utilisateur.nom}</p>
            <span className="inline-block rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-semibold text-citron">{utilisateur.role_libelle}</span>
            <button type="button" onClick={deconnecter} className="flex items-center gap-2 font-semibold text-white/80 hover:text-white"><LogOut size={14} /> Se déconnecter</button>
            <BandeauVersion className="!text-white/50" />
          </div>
        </aside>
        {/* key = centre : changer de centre recharge entièrement la page affichée (aucune donnée de l'ancien centre ne reste à l'écran) */}
        <main key={centreChoisi || "aucun"} className="min-w-0 p-4 sm:p-6 lg:p-8">
          {sansCentre && !pageLibre ? (
            <div className="mx-auto mt-10 max-w-md rounded-2xl bg-white p-6 text-center ring-1 ring-encre/5">
              <Building2 size={40} className="mx-auto text-citron" />
              <h1 className="mt-3 text-xl font-semibold">Choisissez un centre</h1>
              <p className="mt-2 text-sm text-ardoise">Votre compte couvre plusieurs centres : choisissez celui où vous travaillez dans la liste « Centre » de la barre latérale.</p>
            </div>
          ) : <Outlet />}
        </main>
      </div>
    </ProtectionEcran>
  );
}
