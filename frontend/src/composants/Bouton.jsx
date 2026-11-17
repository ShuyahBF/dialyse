// Bouton avec PICTOGRAMME et légende (règle 15) : jamais de bouton sans pictogramme. Variantes colorées sobres (règle 16).
const STYLES = {
  principal: "bg-turquoise-600 text-white hover:bg-turquoise-700",
  vert: "bg-emerald-600 text-white hover:bg-emerald-700",
  rouge: "bg-rose-600 text-white hover:bg-rose-700",
  orange: "bg-orange-500 text-white hover:bg-orange-600",
  neutre: "bg-white text-nuit border border-slate-300 hover:bg-slate-100",
};

export default function Bouton({ icone: Icone, children, variante = "neutre", petit = false, attente = false, ...props }) {
  return (
    <button {...props} disabled={props.disabled || attente}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:opacity-50 disabled:cursor-not-allowed ${petit ? "px-2.5 py-1.5 text-sm" : "px-3.5 py-2"} ${STYLES[variante]} ${props.className || ""}`}>
      {attente ? <span className="jauge" /> : Icone && <Icone size={petit ? 16 : 18} />}
      {children}
    </button>
  );
}

/** Pictogramme seul dans une ligne de tableau : info-bulle et libellé d'accessibilité obligatoires (règle 15). */
export function BoutonIcone({ icone: Icone, libelle, couleur = "text-turquoise-700", ...props }) {
  return (
    <button {...props} aria-label={libelle} title={libelle} className={`rounded-lg p-1.5 hover:bg-slate-100 ${couleur}`}>
      <Icone size={18} />
    </button>
  );
}
