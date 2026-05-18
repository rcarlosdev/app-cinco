"use client";

import { memo, useEffect, useState } from "react";
import {
  Bot,
  Copy,
  FileText,
  ImageIcon,
  LayoutPanelLeft,
  Paperclip,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import type { IADevAction } from "@/services/ia-dev.service";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import BasicMarkdown from "@/modules/agente-ia/components/BasicMarkdown";

type MessageListProps = {
  messages: ChatMessageModel[];
  isBusy: boolean;
  activeDashboardMessageId: string | null;
  onActionClick: (action: IADevAction) => void;
  onShowDashboard: (messageId: string) => void;
  onCopyMessage: (messageId: string) => void;
  onPrepareRelatedQuery: () => void;
};

const getAssistantText = (message: ChatMessageModel) => {
  if (message.status === "streaming") return message.content || "Pensando...";
  return (
    message.normalized?.summary ||
    message.content ||
    "Respuesta generada sin contenido visible."
  );
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
              className="ml-auto max-w-[92%] rounded-[24px] rounded-br-md bg-[#111827] px-4 py-3 text-sm text-white shadow-sm"
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

        return (
          <article
            key={message.id}
            className={`mr-auto max-w-[94%] rounded-[24px] rounded-bl-md border px-4 py-3 text-sm shadow-sm ${
              message.status === "error"
                ? "border-red-200 bg-red-50 text-red-800 dark:border-red-700 dark:bg-red-950/35 dark:text-red-200"
                : "border-gray-200 bg-white text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200"
            }`}
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.16em] text-gray-500 uppercase dark:text-gray-400">
                <Bot size={12} />
                Asistente
                {message.status === "streaming" && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200">
                    <Sparkles size={10} />
                    Streaming
                  </span>
                )}
              </div>

              {showMessageTools ? (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => onShowDashboard(message.id)}
                    aria-label="Mostrar dashboard asociado a esta respuesta"
                    title="Mostrar dashboard asociado"
                    className={`rounded-full border p-2 text-xs transition ${
                      isActiveDashboard
                        ? "border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/30 dark:bg-sky-500/10 dark:text-sky-200"
                        : "border-gray-200 bg-gray-50 text-gray-600 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    }`}
                  >
                    <LayoutPanelLeft size={14} />
                  </button>
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

            <BasicMarkdown content={getAssistantText(message)} />

            {message.status !== "error" && showMessageTools && (
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={onPrepareRelatedQuery}
                  className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-700 transition hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                >
                  <WandSparkles size={12} />
                  Nueva consulta relacionada
                </button>
              </div>
            )}

            {visibleActions.length > 0 && (
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
            )}
          </article>
        );
      })}
    </div>
  );
};

export default memo(MessageList);
