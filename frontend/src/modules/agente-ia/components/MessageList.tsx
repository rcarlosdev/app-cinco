"use client";

import { memo, useEffect, useState } from "react";
import {
  Bot,
  Copy,
  FileText,
  ImageIcon,
  LayoutPanelLeft,
  Paperclip,
  WandSparkles,
} from "lucide-react";
import type { IADevAction } from "@/services/ia-dev.service";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import BasicMarkdown from "@/modules/agente-ia/components/BasicMarkdown";
import type { AgenteIAViewMode } from "@/modules/agente-ia/types";

type MessageListProps = {
  mode?: AgenteIAViewMode;
  messages: ChatMessageModel[];
  isBusy: boolean;
  activeDashboardMessageId: string | null;
  onActionClick: (action: IADevAction) => void;
  onShowDashboard: (messageId: string) => void;
  onCopyMessage: (messageId: string) => void;
  onPrepareRelatedQuery: () => void;
};

const getAssistantText = (message: ChatMessageModel, mode: AgenteIAViewMode) => {
  if (message.status === "streaming") return "Preparando una respuesta...";

  const candidate =
    message.normalized?.summary ||
    message.content ||
    "Ya tengo una respuesta lista.";

  const compact = candidate.replace(/\r/g, "").trim();
  if (!compact) {
    return "Ya tengo una respuesta lista.";
  }

  if (/^[\[{]/.test(compact)) {
    return mode === "user"
      ? "Encontre resultados y el detalle esta disponible en el panel lateral."
      : "Prepare la respuesta y el detalle estructurado esta disponible en el panel de analisis.";
  }

  const filtered = compact
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => {
      if (!line) return false;
      if (/[A-Za-z]:\\|\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-/]+/.test(line)) return false;
      if (
        /\b(runtime|orchestrator|selected_agent|selected_tool|selected_capability|background_run_id|task_state|validation_status|fallback_reason|semantic_explanation|payload|metadata|planner|sql_assisted|legacy_fallback|trace)\b/i.test(
          line,
        )
      ) {
        return false;
      }
      return true;
    })
    .join("\n");

  if (filtered) return filtered;

  return mode === "user"
    ? "Encontre resultados y deje el detalle listo en el panel lateral."
    : "Prepare la respuesta y el detalle ampliado esta disponible en el panel de analisis.";
};

const getActionKey = (action: IADevAction, index: number) => {
  const explicitId = typeof action.id === "string" ? action.id.trim() : "";
  return explicitId || `${action.type || "action"}-${action.label}-${index}`;
};

const isConfirmableSuggestion = (action: IADevAction) => {
  const type = String(action.type || "").trim();
  return Boolean(
    action.label &&
      type !== "create_ticket" &&
      type !== "render_chart" &&
      type !== "memory_review",
  );
};

const formatAttachmentSize = (size: number) => {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

const MessageList = ({
  mode = "dev",
  messages,
  isBusy,
  activeDashboardMessageId,
  onActionClick,
  onShowDashboard,
  onCopyMessage,
  onPrepareRelatedQuery,
}: MessageListProps) => {
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

  return (
    <div className="space-y-4">
      {messages.map((message) => {
        if (message.role === "user") {
          return (
            <article
              key={message.id}
              className="ml-auto max-w-[92%] rounded-[24px] rounded-br-md border border-slate-900 bg-slate-900 px-4 py-3 text-sm text-white shadow-sm dark:border-slate-700 dark:bg-slate-800"
            >
              {message.attachments && message.attachments.length > 0 ? (
                <div className="mb-3 space-y-2">
                  <div className="inline-flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-1 text-[10px] font-semibold tracking-[0.14em] uppercase text-white/80">
                    <Paperclip size={11} />
                    Adjuntos
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {message.attachments.map((attachment) => {
                      const Icon =
                        attachment.kind === "image" ? ImageIcon : FileText;

                      return (
                        <div
                          key={attachment.id}
                          className="inline-flex max-w-full items-center gap-2 rounded-2xl border border-white/10 bg-white/10 px-3 py-2"
                        >
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/10 text-white">
                            <Icon size={15} />
                          </div>
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-white">
                              {attachment.name}
                            </div>
                            <div className="text-[11px] text-white/65">
                              {formatAttachmentSize(attachment.size)}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}
              <BasicMarkdown content={message.content} className="text-white" />
            </article>
          );
        }

        const visibleActions = (message.actions || []).filter(
          (action) => action.type !== "render_chart",
        );
        const showMessageTools = message.id !== "assistant-initial";
        const isActiveDashboard = activeDashboardMessageId === message.id;
        const showDetailsButton =
          mode === "user" &&
          showMessageTools &&
          (Boolean(message.normalized?.hasStructuredContent) ||
            Boolean(message.response));

        return (
          <article
            key={message.id}
            className={`mr-auto max-w-[94%] rounded-[24px] rounded-bl-md border px-4 py-3 text-sm shadow-sm ${
              message.status === "error"
                ? "border-red-200 bg-red-50 text-red-800 dark:border-red-700 dark:bg-red-950/35 dark:text-red-200"
                : "border-gray-200 bg-white/95 text-gray-700 dark:border-gray-800 dark:bg-gray-900/90 dark:text-gray-200"
            }`}
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.16em] text-gray-500 uppercase dark:text-gray-400">
                <Bot size={12} />
                {mode === "user" ? "Asistente" : "Agente IA"}
              </div>

              {showMessageTools ? (
                <div className="flex items-center gap-1">
                  {showDetailsButton ? (
                    <button
                      type="button"
                      onClick={() => onShowDashboard(message.id)}
                      aria-label="Ver detalles relacionados con esta respuesta"
                      title="Ver detalles"
                      className={`rounded-full border px-3 py-1.5 text-xs transition ${
                        isActiveDashboard
                          ? "border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/30 dark:bg-sky-500/10 dark:text-sky-200"
                          : "border-gray-200 bg-gray-50 text-gray-600 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                      }`}
                    >
                      <span className="inline-flex items-center gap-1">
                        <LayoutPanelLeft size={14} />
                        Ver detalles
                      </span>
                    </button>
                  ) : mode === "dev" ? (
                    <button
                      type="button"
                      onClick={() => onShowDashboard(message.id)}
                      aria-label="Abrir panel de analisis asociado a esta respuesta"
                      title="Abrir panel de analisis"
                      className={`rounded-full border p-2 text-xs transition ${
                        isActiveDashboard
                          ? "border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/30 dark:bg-sky-500/10 dark:text-sky-200"
                          : "border-gray-200 bg-gray-50 text-gray-600 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                      }`}
                    >
                      <LayoutPanelLeft size={14} />
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => onCopyMessage(message.id)}
                    aria-label="Copiar respuesta"
                    title="Copiar respuesta"
                    className="rounded-full border border-gray-200 bg-gray-50 p-2 text-xs text-gray-600 transition hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                  >
                    <Copy size={14} />
                  </button>
                </div>
              ) : null}
            </div>

            <BasicMarkdown content={getAssistantText(message, mode)} />

            {message.status !== "error" && showMessageTools ? (
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={onPrepareRelatedQuery}
                  className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-700 transition hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                >
                  <WandSparkles size={12} />
                  {mode === "user" ? "Continuar" : "Profundizar"}
                </button>
              </div>
            ) : null}

            {visibleActions.length > 0 ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {visibleActions.map((action, index) => {
                  const actionKey = getActionKey(action, index);
                  const isConfirming = confirmingActionId === actionKey;

                  return (
                    <button
                      key={actionKey}
                      type="button"
                      disabled={isBusy}
                      onClick={() => {
                        if (!isConfirmableSuggestion(action)) {
                          onActionClick(action);
                          return;
                        }

                        if (!isConfirming) {
                          setConfirmingActionId(actionKey);
                          return;
                        }

                        setConfirmingActionId(null);
                        onActionClick(action);
                      }}
                      className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                        isConfirming
                          ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-200"
                          : "border-gray-300 bg-gray-50 text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                      } disabled:cursor-not-allowed disabled:opacity-60`}
                    >
                      {isConfirming ? `Confirmar: ${action.label}` : action.label}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </article>
        );
      })}
    </div>
  );
};

export default memo(MessageList);
