// Page de connexion : carte centrée, état du serveur, version, œil sur le mot de passe, 2FA, attente avec « Patientez… ».
import { Activity, LogIn, ServerCrash, ServerCog } from "lucide-react";
import { useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import ChampMotDePasse from "../composants/ChampMotDePasse.jsx";
import { Champ, Texte } from "../composants/Champs.jsx";
import { api, jeton } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";

export default function Connexion() {
  const { setUtilisateur, toast, retirer } = useApp();
  const [login, setLogin] = useState("");
  const [mdp, setMdp] = useState("");
  const [code, setCode] = useState("");
  const [besoinCode, setBesoinCode] = useState(false);
  const [attente, setAttente] = useState(false);
  const [etat, setEtat] = useState("verification");      // verification | actif | lent | injoignable

  // État du serveur : « Serveur actif », lent (> 3 s) ou injoignable.
  useEffect(() => {
    const debut = Date.now();
    api("/api/sante", { avecJeton: false })
      .then((s) => setEtat(s.base === "ok" ? (Date.now() - debut > 3000 ? "lent" : "actif") : "injoignable"))
      .catch(() => setEtat("injoignable"));
  }, []);

  async function envoyer(e) {
    e.preventDefault();
    setAttente(true);
    const id = toast("Patientez… connexion en cours", "attente");
    try {
      const r = await api("/auth/login", { methode: "POST", avecJeton: false, corps: { login, mot_de_passe: mdp, code_2fa: code } });
      jeton.ecrire(r.jeton);
      setUtilisateur(await api("/me"));
    } catch (err) {
      if (err.message === "CODE_2FA_REQUIS") { setBesoinCode(true); toast("Saisissez le code de votre application d'authentification", "info"); }
      else toast(err.message, "erreur");
    } finally { retirer(id); setAttente(false); }
  }

  const etats = {
    verification: { txt: "Vérification du serveur…", cl: "text-slate-500", Ic: ServerCog },
    actif: { txt: "Serveur actif", cl: "text-emerald-700", Ic: ServerCog },
    lent: { txt: "Serveur lent à répondre", cl: "text-orange-700", Ic: ServerCog },
    injoignable: { txt: "Serveur injoignable", cl: "text-rose-700", Ic: ServerCrash },
  }[etat];

  return (
    <div className="min-h-dvh flex items-center justify-center p-4 bg-gradient-to-br from-sky-100 via-white to-turquoise-100">
      <form onSubmit={envoyer} className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex flex-col items-center mb-5">
          <div className="rounded-2xl bg-turquoise-600 p-3 text-white mb-2"><Activity size={32} /></div>
          <h1 className="text-xl font-semibold">Dialyse</h1>
          <p className="text-sm text-slate-500">Gestion des actes de dialyse</p>
        </div>
        <Texte libelle="Identifiant" valeur={login} onChange={setLogin} autoComplete="username" placeholder="awa.badini" autoFocus />
        <Champ libelle="Mot de passe"><ChampMotDePasse valeur={mdp} onChange={setMdp} /></Champ>
        {besoinCode && <Texte libelle="Code de vérification (6 chiffres)" valeur={code} onChange={setCode} inputMode="numeric" autoComplete="one-time-code" placeholder="123456" />}
        <Bouton type="submit" variante="principal" icone={LogIn} attente={attente} className="w-full" disabled={!login || !mdp}>Se connecter</Bouton>
        <p className={`mt-4 flex items-center justify-center gap-1.5 text-sm ${etats.cl}`}><etats.Ic size={16} /> {etats.txt}</p>
        <BandeauVersion className="text-center mt-1" />
      </form>
    </div>
  );
}
