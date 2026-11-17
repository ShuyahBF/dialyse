// Pile de toasts : « … en cours » avec jauge circulaire (attente), puis résultat (vert) ou erreur (rouge).
import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import { useApp } from "../lib/contexte.jsx";

export default function Toasts() {
  const { toasts } = useApp();
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`flex items-start gap-2 rounded-2xl border-l-4 px-4 py-3 text-sm shadow-lg ${t.type === "erreur" ? "border-red-500 bg-white text-encre" : t.type === "ok" ? "border-emeraude bg-white text-encre" : t.type === "attente" ? "border-citron bg-encre/90 text-white backdrop-blur" : "border-encre-600 bg-white text-encre"}`}>
          {t.type === "attente" ? <span className="jauge mt-0.5 !border-white/30 !border-t-citron" /> : t.type === "erreur" ? <AlertCircle size={18} className="text-red-500" /> : t.type === "ok" ? <CheckCircle2 size={18} className="text-emeraude" /> : <Info size={18} />}
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}
