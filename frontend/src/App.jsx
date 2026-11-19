// Routes de l'application : connexion si non connecté ; changement de mot de passe obligatoire après réinitialisation.
import { Navigate, Route, Routes } from "react-router-dom";
import MiseEnPage from "./composants/MiseEnPage.jsx";
import Toasts from "./composants/Toasts.jsx";
import { useApp } from "./lib/contexte.jsx";
import Centres from "./pages/Centres.jsx";
import Compte from "./pages/Compte.jsx";
import Connexion from "./pages/Connexion.jsx";
import Facturation from "./pages/Facturation.jsx";
import Journal from "./pages/Journal.jsx";
import Patients from "./pages/Patients.jsx";
import Planning from "./pages/Planning.jsx";
import Postes from "./pages/Postes.jsx";
import Reinitialiser from "./pages/Reinitialiser.jsx";
import Rapports from "./pages/Rapports.jsx";
import Suivi from "./pages/Suivi.jsx";
import ModelesAdhesion from "./pages/ModelesAdhesion.jsx";
import Sauvegardes from "./pages/Sauvegardes.jsx";
import Stock from "./pages/Stock.jsx";
import Tableau from "./pages/Tableau.jsx";
import Utilisateurs from "./pages/Utilisateurs.jsx";

export default function App() {
  const { utilisateur, pret } = useApp();
  if (!pret) return <div className="min-h-dvh flex items-center justify-center"><span className="jauge" /></div>;
  const role = utilisateur?.role;
  const accueil = ["secretariat"].includes(role) ? "/planning" : role === "technicien" ? "/postes" : "/";
  return (
    <>
      {!utilisateur ? (
        <Routes><Route path="reinitialiser" element={<Reinitialiser />} /><Route path="*" element={<Connexion />} /></Routes>
      ) : (
        <Routes>
          <Route element={<MiseEnPage />}>
            <Route index element={role === "secretariat" || role === "technicien" ? <Navigate to={accueil} replace /> : <Tableau />} />
            <Route path="planning" element={<Planning />} />
            <Route path="patients" element={<Patients />} />
            <Route path="postes" element={<Postes />} />
            <Route path="facturation" element={<Facturation />} />
            <Route path="rapports" element={<Rapports />} />
            <Route path="suivi" element={<Suivi />} />
            <Route path="modeles" element={<ModelesAdhesion />} />
            <Route path="sauvegardes" element={<Sauvegardes />} />
            <Route path="stock" element={<Stock />} />
            <Route path="centres" element={<Centres />} />
            <Route path="utilisateurs" element={<Utilisateurs />} />
            <Route path="journal" element={<Journal />} />
            <Route path="compte" element={<Compte />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      )}
      <Toasts />
    </>
  );
}
