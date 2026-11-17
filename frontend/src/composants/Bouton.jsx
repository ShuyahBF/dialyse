// Bouton avec PICTOGRAMME et légende (règle 15) : jamais de bouton sans pictogramme. Variantes colorées sobres (règle 16).
const STYLES = {
  principal: "bg-emeraude text-white hover:bg-emeraude-600",
  vert: "bg-emerald-600 text-white hover:bg-emerald-700",
  rouge: "bg-rose-600 text-white hover:bg-rose-700",
  orange: "bg-citron text-white hover:bg-citron-600",
  neutre: "bg-white text-encre ring-1 ring-encre/15 hover:ring-encre/40",
};

export default function Bouton({ icone: Icone, children, variante = "neutre", petit = false, attente = false, ...props }) {
  return (
    <button {...props} disabled={props.disabled || attente}
      className={`inline-flex items-center justify-center gap-2 rounded-full font-semibold transition active:translate-y-px disabled:opacity-50 disabled:cursor-not-allowed ${petit ? "px-3.5 py-1.5 text-sm" : "px-5 py-2.5"} ${STYLES[variante]} ${props.className || ""}`}>
      {attente ? <span className="jauge" /> : Icone && <Icone size={petit ? 16 : 18} />}
      {children}
    </button>
  );
}

/** Pictogramme seul dans une ligne de tableau : info-bulle et libellé d'accessibilité obligatoires (règle 15). */
export function BoutonIcone({ icone: Icone, libelle, couleur = "text-emeraude", ...props }) {
  return (
    <button {...props} aria-label={libelle} title={libelle} className={`rounded-full p-1.5 hover:bg-emeraude-50 ${couleur}`}>
      <Icone size={18} />
    </button>
  );
}
