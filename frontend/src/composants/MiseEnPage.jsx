// Cadre du portail (présentation ZandGo) : barre latérale bleu nuit de 230 px (logo, menus à pictogrammes, élément actif en orange,
// nom + rôle en pastille, déconnexion, version), menu replié derrière un bouton « Menu » sur téléphone. Majuscule à chaque mot (règle 18).
import { BarChart3, CalendarDays, ClipboardList, DatabaseBackup, LayoutDashboard, LogOut, Menu, Monitor, Package, Receipt, ShieldCheck, UserCog, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useApp } from "../lib/contexte.jsx";
import { titreMenu } from "../lib/format.js";
import BandeauVersion from "./BandeauVersion.jsx";
import Logo from "./Logo.jsx";
import ProtectionEcran from "./ProtectionEcran.jsx";

// Chaque entrée : chemin, libellé, pictogramme, rôles autorisés (liste vide = tous).
const MENU = [
  { chemin: "/", libelle: "tableau de bord", icone: LayoutDashboard, roles: ["super_admin", "admin", "direction", "medecin", "infirmier"] },
  { chemin: "/rapports", libelle: "rapports", icone: BarChart3, roles: ["super_admin", "admin", "direction", "medecin", "infirmier"] },
  { chemin: "/planning", libelle: "planning des séances", icone: CalendarDays, roles: ["super_admin", "admin", "medecin", "infirmier", "secretariat"] },
  { chemin: "/patients", libelle: "patients", icone: Users, roles: ["super_admin", "admin", "medecin", "infirmier", "secretariat"] },
  { chemin: "/postes", libelle: "postes de dialyse", icone: Monitor, roles: [] },
  { chemin: "/stock", libelle: "consommables et stocks", icone: Package, roles: ["super_admin", "admin", "medecin", "infirmier", "technicien"] },
  { chemin: "/facturation", libelle: "facturation", icone: Receipt, roles: ["super_admin", "admin", "secretariat"] },
  { chemin: "/utilisateurs", libelle: "gestion des comptes", icone: UserCog, roles: ["super_admin", "admin"] },
  { chemin: "/journal", libelle: "journal d'audit", icone: ClipboardList, roles: ["super_admin", "admin"] },
  { chemin: "/sauvegardes", libelle: "sauvegardes chiffrées", icone: DatabaseBackup, roles: ["super_admin", "admin"] },
  { chemin: "/compte", libelle: "mon compte", icone: ShieldCheck, roles: [] },
];

export default function MiseEnPage() {
  const { utilisateur, deconnecter } = useApp();
  const { pathname } = useLocation();
  const [ouvert, setOuvert] = useState(false);            // menu replié sur téléphone, refermé après chaque choix
  useEffect(() => setOuvert(false), [pathname]);
  const entrees = MENU.filter((m) => m.roles.length === 0 || m.roles.includes(utilisateur.role));
  return (
    <ProtectionEcran>
      <div className="min-h-screen overflow-x-clip md:grid md:grid-cols-[230px_1fr]">
        <aside className="barre-laterale sticky top-0 z-40 flex max-h-screen flex-col gap-1 overflow-y-auto bg-encre p-4 text-white md:h-screen md:overscroll-contain">
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
                <Icone size={18} className="shrink-0" /> {titreMenu(libelle)}
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
        <main className="min-w-0 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </ProtectionEcran>
  );
}
