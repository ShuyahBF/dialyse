// Page ouverte depuis le lien WhatsApp « mot de passe oublié » : choix du nouveau mot de passe (œil sur les deux champs, lien à usage unique).
import { KeyRound } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import ChampMotDePasse from "../composants/ChampMotDePasse.jsx";
import ForceMotDePasse from "../composants/ForceMotDePasse.jsx";
import { Champ } from "../composants/Champs.jsx";
import Logo from "../composants/Logo.jsx";
import { api } from "../lib/api.js";
import { motDePasseAssezFort } from "../lib/motdepasse.js";
import { useApp } from "../lib/contexte.jsx";

export default function Reinitialiser() {
  const [params] = useSearchParams();
  const { avecToast } = useApp();
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [fini, setFini] = useState(false);
  const faible = !motDePasseAssezFort(a);
  const enregistrer = async () => {
    await avecToast("Enregistrement du mot de passe", () => api("/auth/reinitialiser", { methode: "POST", avecJeton: false, corps: { jeton: params.get("jeton") || "", mot_de_passe: a } }), () => "Mot de passe modifié");
    setFini(true);
  };
  return (
    <div className="grid min-h-screen place-items-center bg-encre px-4 py-10">
      <main className="w-full max-w-sm rounded-3xl bg-white p-6 shadow-2xl sm:p-8">
        <div className="flex flex-col items-center mb-4"><Logo taille={40} /><h1 className="mt-5 font-editorial text-2xl font-bold italic">Nouveau mot de passe</h1></div>
        {fini ? (
          <><p className="text-sm text-emerald-700 mb-3">Mot de passe modifié. Vos clés d'accès et empreintes enregistrées ont été retirées : vous pourrez les recréer après connexion.</p><Link to="/" className="text-turquoise-700 underline">Retour à la connexion</Link></>
        ) : (
          <>
            <Champ libelle="Nouveau mot de passe" aide="8 caractères au moins, avec une lettre et un chiffre"><ChampMotDePasse valeur={a} onChange={setA} autoComplete="new-password" /></Champ>
            <ForceMotDePasse valeur={a} />
            <Champ libelle="Confirmer le mot de passe"><ChampMotDePasse valeur={b} onChange={setB} autoComplete="new-password" /></Champ>
            {b && a !== b && <p className="text-sm text-rose-700 mb-2">Les deux mots de passe sont différents.</p>}
            <Bouton icone={KeyRound} variante="principal" className="w-full" disabled={faible || a !== b || !params.get("jeton")} onClick={enregistrer}>Enregistrer</Bouton>
          </>
        )}
        <BandeauVersion className="text-center mt-4" />
      </main>
    </div>
  );
}
