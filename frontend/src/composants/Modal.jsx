// UN SEUL composant de fenêtre modale (règle 11) : 28 rem (md) ou 36 rem (xl) au plus, 85 % de la hauteur, défilement DANS la fenêtre.
import { X } from "lucide-react";
import { useEffect } from "react";

export default function Modal({ titre, onFermer, large = false, children, pied }) {
  // Échap ferme la fenêtre.
  useEffect(() => {
    const f = (e) => e.key === "Escape" && onFermer();
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [onFermer]);
  return (
    <div className="fixed inset-0 z-40 flex items-end sm:items-center justify-center bg-nuit/50 p-2 sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onFermer()}>
      <div role="dialog" aria-modal="true" aria-label={titre}
        className={`w-full ${large ? "max-w-xl" : "max-w-md"} max-h-[85dvh] flex flex-col rounded-2xl bg-white shadow-2xl`}>
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h2 className="text-lg font-semibold">{titre}</h2>
          <button onClick={onFermer} aria-label="Fermer" title="Fermer" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100">
            <X size={20} />
          </button>
        </div>
        <div className="overflow-y-auto px-4 py-3 flex-1">{children}</div>
        {pied && <div className="border-t border-slate-200 px-4 py-3 flex flex-wrap gap-2 justify-end">{pied}</div>}
      </div>
    </div>
  );
}
