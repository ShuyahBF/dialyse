// Pile de toasts : « … en cours » avec jauge circulaire (attente), puis résultat (vert) ou erreur (rouge).
import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import { useApp } from "../lib/contexte.jsx";

export default function Toasts() {
  const { toasts } = useApp();
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`flex items-start gap-2 rounded-xl px-4 py-3 shadow-lg text-sm text-white ${t.type === "erreur" ? "bg-rose-600" : t.type === "ok" ? "bg-emerald-600" : t.type === "attente" ? "bg-turquoise-700" : "bg-nuit"}`}>
          {t.type === "attente" ? <span className="jauge mt-0.5 !border-white/30 !border-t-white" /> : t.type === "erreur" ? <AlertCircle size={18} /> : t.type === "ok" ? <CheckCircle2 size={18} /> : <Info size={18} />}
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}
