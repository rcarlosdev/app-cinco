"use client";

import { memo, useEffect, useState } from "react";
import { Bot } from "lucide-react";
import type { IADevAction } from "@/services/ia-dev.service";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import ResponseRenderer from "@/modules/programacion/ia-dev/chat/components/ResponseRenderer";
import StreamingMessage from "@/modules/programacion/ia-dev/chat/components/StreamingMessage";

type AssistantMessageProps = {
  message: ChatMessageModel;
  onActionClick: (action: IADevAction) => void;
  isBusy: boolean;
  variant?: "full" | "clean";
};

const getActionKey = (action: IADevAction, index?: number) => {
  const explicitId = typeof action.id === "string" ? action.id.trim() : "";
  if (explicitId) return explicitId;
  return `${action.type || "action"}-${action.label || "sin-label"}-${index ?? 0}`;
};

const isConfirmableSuggestion = (action: IADevAction) => {
  const type = String(action.type || "").trim();
  if (
    type === "create_ticket" ||
    type === "render_chart" ||
    type === "memory_review"
  ) {
    return false;
  }
  return Boolean(String(action.label || "").trim());
};

const AssistantMessage = ({
  message,
  onActionClick,
  isBusy,
  variant = "full",
}: AssistantMessageProps) => {
  const visibleActions = (message.actions || []).filter(
    (action) => action.type !== "render_chart",
  );
  const showRuntimeDetails = variant === "full";
  const [confirmingActionId, setConfirmingActionId] = useState<string | null>(
    null,
  );

  useEffect(() => {
    if (!confirmingActionId) return;
    const timeoutId = window.setTimeout(() => {
      setConfirmingActionId(null);
    }, 3500);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [confirmingActionId]);

  const handleVisibleActionClick = (action: IADevAction, actionKey: string) => {
    if (!isConfirmableSuggestion(action)) {
      onActionClick(action);
      return;
    }

    if (confirmingActionId !== actionKey) {
      setConfirmingActionId(actionKey);
      return;
    }

    setConfirmingActionId(null);
    onActionClick(action);
  };

  return (
    <article
      className={`shadow-theme-xs mr-auto max-w-[95%] rounded-2xl rounded-bl-md border px-4 py-3 text-sm ${
        message.status === "error"
          ? "border-red-200 bg-red-50 text-red-800 dark:border-red-700 dark:bg-red-950/35 dark:text-red-200"
          : "border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-800/95 dark:text-gray-200"
      }`}
    >
      <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold tracking-wide uppercase opacity-80">
        <Bot size={12} />
        Asistente IA
      </div>

      <ResponseRenderer message={message} variant={variant} />

      {message.status === "streaming" && <StreamingMessage />}

      {showRuntimeDetails &&
        message.pendingProposals &&
        message.pendingProposals.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
            {message.pendingProposals.slice(0, 6).map((proposal) => (
              <span
                key={proposal.proposal_id}
                className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300"
                title={`${proposal.proposal_id} | ${proposal.status}`}
              >
                {proposal.status}
              </span>
            ))}
          </div>
        )}

      {showRuntimeDetails &&
        message.memoryCandidates &&
        message.memoryCandidates.length > 0 && (
          <div className="mt-3 rounded-lg border border-gray-200 bg-white/70 px-3 py-2 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-900/70 dark:text-gray-300">
            Candidatos de memoria detectados: {message.memoryCandidates.length}.
            Puedes revisarlos en el panel Memoria y Workflow.
          </div>
        )}

      {visibleActions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {visibleActions.map((action, index) => {
            const actionKey = getActionKey(action, index);
            const isConfirming = confirmingActionId === actionKey;

            return (
              <button
                key={actionKey}
                type="button"
                onClick={() => handleVisibleActionClick(action, actionKey)}
                className={`inline-flex items-center gap-2 rounded-md border px-2 py-1 text-xs font-semibold transition disabled:opacity-60 ${
                  isConfirming
                    ? "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-400/40 dark:bg-amber-400/10 dark:text-amber-200"
                    : "border-brand-300 bg-brand-500/10 text-brand-700 hover:bg-brand-500/20 dark:border-brand-700 dark:text-brand-300"
                }`}
                disabled={isBusy}
                title={
                  isConfirmableSuggestion(action)
                    ? "Primer clic confirma. Segundo clic ejecuta la consulta."
                    : action.label
                }
              >
                <span>{action.label}</span>
                {isConfirming && (
                  <span className="rounded-full bg-amber-200/80 px-1.5 py-0.5 text-[10px] font-bold text-amber-900 dark:bg-amber-300/20 dark:text-amber-100">
                    Confirmar
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {confirmingActionId && (
        <p className="mt-2 text-[11px] text-amber-700 dark:text-amber-200">
          Clic de nuevo en la misma sugerencia para ejecutarla.
        </p>
      )}
    </article>
  );
};

export default memo(AssistantMessage);
