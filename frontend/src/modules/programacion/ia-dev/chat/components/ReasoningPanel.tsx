"use client";

import { BrainCircuit, Compass, Sparkles } from "lucide-react";
import type { IADevChatResponse } from "@/services/ia-dev.service";

type ReasoningPanelProps = {
  response?: Partial<IADevChatResponse>;
  isStreaming?: boolean;
};

const confidenceLabel = (value: number | null | undefined) => {
  if (typeof value !== "number") return null;
  if (value >= 0.85) return "alta";
  if (value >= 0.65) return "media";
  return "explorando";
};

const shorten = (value: string, max = 140) => {
  const text = String(value || "").trim();
  if (!text) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, max - 3).trimEnd()}...`;
};

const ReasoningPanel = ({
  response,
  isStreaming = false,
}: ReasoningPanelProps) => {
  const updates = Array.isArray(response?.working_updates)
    ? response?.working_updates.filter(
        (item) => Boolean(item?.display_text || item?.summary),
      )
    : [];
  const reasoning = response?.reasoning;
  const hypotheses = Array.isArray(reasoning?.hypotheses)
    ? reasoning?.hypotheses
    : [];
  const diagnostics = Array.isArray(reasoning?.diagnostics)
    ? reasoning?.diagnostics
    : [];

  const topHypothesis = hypotheses.find(
    (item) => String(item?.status || "").toLowerCase() === "supported",
  );
  const topDiagnostic = diagnostics[0];

  if (
    !isStreaming &&
    updates.length === 0 &&
    !topHypothesis &&
    !topDiagnostic
  ) {
    return null;
  }

  return (
    <section className="space-y-3 rounded-2xl border border-emerald-200/80 bg-gradient-to-br from-emerald-50 via-white to-cyan-50 px-3 py-3 text-xs text-slate-700 dark:border-emerald-900/60 dark:from-emerald-950/30 dark:via-slate-900 dark:to-cyan-950/30 dark:text-slate-200">
      <div className="flex items-center gap-2 text-[11px] font-semibold tracking-wide text-emerald-700 uppercase dark:text-emerald-300">
        <BrainCircuit size={13} />
        Razonamiento en curso
      </div>

      {isStreaming && updates.length === 0 ? (
        <div className="rounded-xl border border-white/70 bg-white/80 px-3 py-2 text-slate-600 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-300">
          Analizando la consulta, conectando contexto y preparando la mejor ruta.
        </div>
      ) : null}

      {updates.length > 0 ? (
        <div className="space-y-2">
          {updates.slice(-4).map((update, index) => {
            const level = confidenceLabel(update.confidence);
            return (
              <div
                key={`${update.stage}-${update.at}-${index}`}
                className="rounded-xl border border-white/70 bg-white/85 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-900/70"
              >
                <div className="mb-1 flex items-center gap-2">
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                    {update.stage_label || update.stage}
                  </span>
                  {level ? (
                    <span className="text-[10px] text-slate-500 dark:text-slate-400">
                      claridad {level}
                    </span>
                  ) : null}
                </div>
                <p className="leading-5 text-slate-700 dark:text-slate-200">
                  {shorten(update.display_text || update.summary)}
                </p>
              </div>
            );
          })}
        </div>
      ) : null}

      {topHypothesis ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50/90 px-3 py-2 text-slate-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-slate-200">
          <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold text-amber-700 dark:text-amber-300">
            <Sparkles size={12} />
            Pista fuerte
          </div>
          <p className="leading-5">{shorten(topHypothesis.text)}</p>
        </div>
      ) : null}

      {topDiagnostic?.recommended_action ? (
        <div className="rounded-xl border border-cyan-200 bg-cyan-50/90 px-3 py-2 text-slate-700 dark:border-cyan-900/60 dark:bg-cyan-950/30 dark:text-slate-200">
          <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold text-cyan-700 dark:text-cyan-300">
            <Compass size={12} />
            Ajuste aprendido
          </div>
          <p className="leading-5">{shorten(topDiagnostic.recommended_action)}</p>
        </div>
      ) : null}

      {reasoning?.current_next_step ? (
        <p className="text-[11px] text-slate-500 dark:text-slate-400">
          Siguiente foco: {shorten(reasoning.current_next_step, 110)}
        </p>
      ) : null}
    </section>
  );
};

export default ReasoningPanel;
