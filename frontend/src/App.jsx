// Routes de l'application : connexion si non connecté ; changement de mot de passe obligatoire après réinitialisation.
import { Navigate, Route, Routes } from "react-router-dom";
import MiseEnPage from "./composants/MiseEnPage.jsx";
import Toasts from "./composants/Toasts.jsx";
import { useApp } from "./lib/contexte.jsx";
import Centres from "./pages/Centres.jsx";
import FicheCentrePage from "./pages/FicheCentre.jsx";
import FondAccueilPage from "./pages/FondAccueil.jsx";
import SyntheseGroupe from "./pages/SyntheseGroupe.jsx";
import Eau from "./pages/Eau.jsx";
import Maintenance from "./pages/Maintenance.jsx";
import Personnel from "./pages/Personnel.jsx";
import Rentabilite from "./pages/Rentabilite.jsx";
import Aujourdhui from "./pages/Aujourdhui.jsx";
import Calendrier from "./pages/Calendrier.jsx";
import Messagerie from "./pages/Messagerie.jsx";
import Reservations from "./pages/Reservations.jsx";
import Compte from "./pages/Compte.jsx";
import Connexion from "./pages/Connexion.jsx";
import ConnexionGoogle from "./pages/ConnexionGoogle.jsx";
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
import PrevisionsStock from "./pages/PrevisionsStock.jsx";
import Stock from "./pages/Stock.jsx";
import Tableau from "./pages/Tableau.jsx";
import Utilisateurs from "./pages/Utilisateurs.jsx";

export default function App() {
  const { utilisateur, pret } = useApp();
  if (!pret) return <div className="min-h-dvh flex items-center justify-center"><span className="jauge" /></div>;
  const role = utilisateur?.role;
  const accueil = ["secretariat"].includes(role) ? "/aujourdhui" : role === "technicien" ? "/postes" : "/";
  return (
    <>
      {!utilisateur ? (
        <Routes><Route path="reinitialiser" element={<Reinitialiser />} /><Route path="connexion-google" element={<ConnexionGoogle />} /><Route path="*" element={<Connexion />} /></Routes>
      ) : (
        <Routes>
          <Route path="connexion-google" element={<ConnexionGoogle />} />
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
            <Route path="stock/previsions" element={<PrevisionsStock />} />
            <Route path="fiche-centre" element={<FicheCentrePage />} />
            <Route path="personnel" element={<Personnel />} />
            <Route path="maintenance" element={<Maintenance />} />
            <Route path="eau" element={<Eau />} />
            <Route path="rentabilite" element={<Rentabilite />} />
            <Route path="aujourdhui" element={<Aujourdhui />} />
            <Route path="calendrier" element={<Calendrier />} />
            <Route path="reservations" element={<Reservations />} />
            <Route path="messagerie" element={<Messagerie />} />
            <Route path="groupe" element={<SyntheseGroupe />} />
            <Route path="centres" element={<Centres />} />
            <Route path="fond-accueil" element={<FondAccueilPage />} />
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
