// Page d'arrivée après Google : « /connexion-google?code=… » (ou ?erreur=…, ?lie=1).
// Le code à usage unique est échangé contre le jeton ; si le compte a la double authentification (application ou WhatsApp), le code est demandé ici :
// Google remplace le mot de passe, pas la sécurité du compte.
import { LogIn, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Bouton from "../composants/Bouton.jsx";
import { Texte } from "../composants/Champs.jsx";
import { api, jeton } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { MESSAGES_GOOGLE } from "../lib/google.js";

export default function ConnexionGoogle() {
  const { setUtilisateur, toast } = useApp();
  const naviguer = useNavigate();
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code"), echec = params.get("erreur"), lie = params.get("lie");
  const [erreur, setErreur] = useState("");
  const [besoin, setBesoin] = useState("");             // "" | "totp" | "wa"
  const [saisie, setSaisie] = useState("");
  const [attente, setAttente] = useState(false);
  const fait = useRef(false);                           // un seul premier échange, même si React redessine la page
  const retour = () => naviguer("/", { replace: true });

  const echanger = async (code2fa = "") => {
    setAttente(true);
    try {
      const r = await api("/auth/google/echange", { methode: "POST", avecJeton: false, corps: { code, code_2fa: code2fa } });
      jeton.ecrire(r.jeton);
      setUtilisateur(await api("/me"));
      naviguer("/", { replace: true });
    } catch (err) {
      if (err.message === "CODE_2FA_REQUIS") { setBesoin("totp"); toast("Saisissez le code de votre application d'authentification", "info"); }
      else if (err.message === "CODE_WA_REQUIS") { setBesoin("wa"); toast("Un code vous a été envoyé par WhatsApp", "info"); }
      else setErreur(err.message);
    } finally { setAttente(false); }
  };

  useEffect(() => {
    if (fait.current) return;
    fait.current = true;
    if (lie) { toast("Compte Google lié : vous pouvez maintenant vous connecter avec Google.", "ok"); naviguer("/compte", { replace: true }); return; }
    if (echec || !code) { setErreur(MESSAGES_GOOGLE[echec] || "Connexion par Google impossible."); return; }
    echanger();
  }, []);                                               // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="mx-auto max-w-md p-6">
      <div className="rounded-2xl bg-white p-5 ring-1 ring-encre/10 space-y-3" data-testid="connexion-google">
        {erreur ? (
          <>
            <p className="rounded-lg bg-rose-50 p-3 text-sm text-rose-900">{erreur}</p>
            <Bouton icone={LogIn} variante="principal" className="w-full" onClick={retour}>Retour à la connexion</Bouton>
          </>
        ) : besoin ? (
          <form onSubmit={(e) => { e.preventDefault(); echanger(saisie); }}>
            <p className="flex items-center gap-2 font-semibold text-emeraude mb-2"><ShieldCheck size={18} />{besoin === "wa" ? "Code reçu par WhatsApp" : "Double authentification"}</p>
            <Texte libelle={besoin === "wa" ? "Code reçu par WhatsApp (6 chiffres)" : "Code de l'application d'authentification (6 chiffres)"} valeur={saisie} onChange={setSaisie} inputMode="numeric" autoComplete="one-time-code" autoFocus />
            <Bouton type="submit" variante="principal" icone={ShieldCheck} attente={attente} className="w-full" disabled={!saisie}>Valider le code</Bouton>
          </form>
        ) : <p className="text-center text-sm text-slate-600">Patientez… connexion par Google en cours.</p>}
      </div>
    </div>
  );
}
