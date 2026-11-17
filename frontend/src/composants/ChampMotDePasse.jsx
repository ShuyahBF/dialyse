// UN SEUL champ de saisie secrète (règle 22) : pictogramme œil dans le champ, masqué par défaut, zone tactile de 44 px.
import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";

export default function ChampMotDePasse({ valeur, onChange, placeholder, autoComplete = "current-password", id }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input id={id} type={visible ? "text" : "password"} value={valeur} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        autoComplete={autoComplete} className="w-full rounded-lg border border-slate-300 px-3 py-2 pr-12 focus:outline-none focus:ring-2 focus:ring-sky-500" />
      <button type="button" onClick={() => setVisible((v) => !v)} aria-label={visible ? "Masquer la saisie" : "Afficher la saisie"}
        title={visible ? "Masquer la saisie" : "Afficher la saisie"} className="absolute right-0 top-0 h-full w-11 flex items-center justify-center text-slate-500 hover:text-nuit">
        {visible ? <EyeOff size={20} /> : <Eye size={20} />}
      </button>
    </div>
  );
}
