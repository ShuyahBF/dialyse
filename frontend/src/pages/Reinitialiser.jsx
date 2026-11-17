// Page ouverte depuis le lien WhatsApp « mot de passe oublié » : choix du nouveau mot de passe (œil sur les deux champs, lien à usage unique).
import { Activity, KeyRound } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import ChampMotDePasse from "../composants/ChampMotDePasse.jsx";
import { Champ } from "../composants/Champs.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";

export default function Reinitialiser() {
  const [params] = useSearchParams();
  const { avecToast } = useApp();
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [fini, setFini] = useState(false);
  const faible = a.length < 8 || !/[a-zA-Z]/.test(a) || !/\d/.test(a);
  const enregistrer = async () => {
    await avecToast("Enregistrement du mot de passe", () => api("/auth/reinitialiser", { methode: "POST", avecJeton: false, corps: { jeton: params.get("jeton") || "", mot_de_passe: a } }), () => "Mot de passe modifié");
    setFini(true);
  };
  return (
    <div className="min-h-dvh flex items-center justify-center p-4 bg-gradient-to-br from-sky-100 via-white to-turquoise-100">
      <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex flex-col items-center mb-4"><div className="rounded-2xl bg-turquoise-600 p-3 text-white mb-2"><Activity size={28} /></div><h1 className="text-xl font-semibold">Nouveau mot de passe</h1></div>
        {fini ? (
          <><p className="text-sm text-emerald-700 mb-3">Mot de passe modifié. Vos clés d'accès et empreintes enregistrées ont été retirées : vous pourrez les recréer après connexion.</p><Link to="/" className="text-turquoise-700 underline">Retour à la connexion</Link></>
        ) : (
          <>
            <Champ libelle="Nouveau mot de passe" aide="8 caractères au moins, avec une lettre et un chiffre"><ChampMotDePasse valeur={a} onChange={setA} autoComplete="new-password" /></Champ>
            <Champ libelle="Confirmer le mot de passe"><ChampMotDePasse valeur={b} onChange={setB} autoComplete="new-password" /></Champ>
            {b && a !== b && <p className="text-sm text-rose-700 mb-2">Les deux mots de passe sont différents.</p>}
            <Bouton icone={KeyRound} variante="principal" className="w-full" disabled={faible || a !== b || !params.get("jeton")} onClick={enregistrer}>Enregistrer</Bouton>
          </>
        )}
        <BandeauVersion className="text-center mt-4" />
      </div>
    </div>
  );
}
