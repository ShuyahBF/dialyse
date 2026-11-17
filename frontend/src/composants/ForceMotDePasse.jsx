// Indicateur de force affiché SOUS le champ pendant la saisie : trois critères qui passent au vert (coche) dès qu'ils sont remplis.
// Jamais la couleur seule : chaque critère a aussi un pictogramme et un texte (règle 16). Rien n'est affiché tant que le champ est vide.
import { Check, Circle } from "lucide-react";
import { criteresMotDePasse } from "../lib/motdepasse.js";

export default function ForceMotDePasse({ valeur }) {
  if (!valeur) return null;
  const criteres = criteresMotDePasse(valeur);
  const ok = criteres.every((c) => c.ok);
  return (
    <ul className="-mt-2 mb-3 space-y-0.5 text-xs" aria-live="polite">
      {criteres.map((c) => (
        <li key={c.id} className={`flex items-center gap-1.5 ${c.ok ? "text-emerald-700" : "text-rose-700"}`}>
          {c.ok ? <Check size={13} /> : <Circle size={13} />}{c.libelle}
        </li>
      ))}
      {ok && <li className="font-semibold text-emerald-700">Mot de passe valide</li>}
    </ul>
  );
}
