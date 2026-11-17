// Mise en page du portail : barre latérale (menus selon le rôle, majuscule à chaque mot : règle 18), en-tête, version affichée.
import { Activity, BarChart3, CalendarDays, ClipboardList, DatabaseBackup, LayoutDashboard, LogOut, Monitor, Package, Receipt, ShieldCheck, UserCog, Users } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useApp } from "../lib/contexte.jsx";
import { titreMenu } from "../lib/format.js";
import BandeauVersion from "./BandeauVersion.jsx";
import ProtectionEcran from "./ProtectionEcran.jsx";

// Chaque entrée : chemin, libellé, pictogramme, rôles autorisés (liste vide = tous).
const MENU = [
  { chemin: "/", libelle: "tableau de bord", icone: LayoutDashboard, roles: ["super_admin", "admin", "direction", "medecin", "infirmier"] },
  { chemin: "/planning", libelle: "planning des séances", icone: CalendarDays, roles: ["super_admin", "admin", "medecin", "infirmier", "secretariat"] },
  { chemin: "/rapports", libelle: "rapports", icone: BarChart3, roles: ["super_admin", "admin", "direction", "medecin", "infirmier"] },
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
  const entrees = MENU.filter((m) => m.roles.length === 0 || m.roles.includes(utilisateur.role));
  return (
    <ProtectionEcran>
      <div className="min-h-dvh flex flex-col md:flex-row">
        <aside className="md:w-64 bg-nuit text-white flex md:flex-col md:min-h-dvh">
          <div className="hidden md:flex items-center gap-2 px-5 py-5 text-lg font-semibold">
            <Activity className="text-sky-300" /> Dialyse
          </div>
          <nav className="flex md:flex-col gap-1 p-2 overflow-x-auto md:overflow-visible flex-1">
            {entrees.map(({ chemin, libelle, icone: Icone }) => (
              <NavLink key={chemin} to={chemin} end={chemin === "/"}
                className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 whitespace-nowrap ${isActive ? "bg-turquoise-600 text-white" : "text-sky-100 hover:bg-white/10"}`}>
                <Icone size={18} /> {titreMenu(libelle)}
              </NavLink>
            ))}
          </nav>
          <div className="hidden md:block p-4 text-sky-200 text-xs border-t border-white/10">
            <div className="font-medium text-white">{utilisateur.nom}</div>
            <div className="mb-2">{utilisateur.role_libelle}</div>
            <button onClick={deconnecter} className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3 py-1.5 text-white hover:bg-white/20">
              <LogOut size={16} /> Se déconnecter
            </button>
            <BandeauVersion className="!text-sky-300 mt-3" />
          </div>
        </aside>
        <main className="flex-1 min-w-0 p-3 sm:p-6">
          <div className="md:hidden flex items-center justify-between mb-3 text-sm">
            <span className="font-medium">{utilisateur.nom}</span>
            <button onClick={deconnecter} className="inline-flex items-center gap-1 text-rose-700"><LogOut size={16} /> Se déconnecter</button>
          </div>
          <Outlet />
          <BandeauVersion className="md:hidden mt-6 text-center" />
        </main>
      </div>
    </ProtectionEcran>
  );
}
