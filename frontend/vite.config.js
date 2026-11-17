// Configuration Vite : la date de compilation et le commit court sont injectés au build (règle 2 : version et date de déploiement affichées).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { execSync } from "node:child_process";

// Commit court du dépôt (vide si git est indisponible au moment du build).
function commitCourt() {
  try { return execSync("git rev-parse --short HEAD").toString().trim(); } catch { return ""; }
}

export default defineConfig({
  plugins: [react()],
  define: {
    __COMMIT__: JSON.stringify(process.env.RENDER_GIT_COMMIT ? process.env.RENDER_GIT_COMMIT.slice(0, 7) : commitCourt()),
  },
  // En développement, les routes de l'API sont relayées vers le serveur local (port 8000). Une navigation de page (Accept: text/html) reste
  // servie par le site : les écrans « /patients », « /postes »… portent le même nom que des routes de l'API.
  server: {
    proxy: Object.fromEntries(["/api", "/auth", "/me", "/roles", "/listes", "/utilisateurs", "/patients", "/postes", "/seances", "/bilans", "/stock", "/factures", "/facturation", "/rapports", "/admin", "/compte", "/tableau", "/historique", "/journal", "/anonyme", "/modeles-adhesion"]
      .map((chemin) => [chemin, { target: "http://localhost:8000", bypass: (req) => (req.headers.accept || "").includes("text/html") ? "/index.html" : undefined }])),
  },
});
