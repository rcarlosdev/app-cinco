"use client";

import type { RefObject } from "react";
import type { IADevAction } from "@/services/ia-dev.service";
import { FileSearch } from "lucide-react";
import type {
  ChatAttachmentSummary,
  ChatMessageModel,
} from "@/modules/programacion/ia-dev/chat/types";
import MessageInput from "@/modules/agente-ia/components/MessageInput";
import MessageList from "@/modules/agente-ia/components/MessageList";
import ScrollToBottomButton from "@/modules/programacion/ia-dev/chat/components/ScrollToBottomButton";
import type { AgenteIAViewMode } from "@/modules/agente-ia/types";

type ChatPanelProps = {
  mode?: AgenteIAViewMode;
  chatTitle: string;
  chatStatus: string;
  streaming: boolean;
  isWorkspaceLayout: boolean;
  activeDashboardMessageId: string | null;
  taskPreparationLabel: string;
  clarificationQuestion: string;
  visibleMessages: ChatMessageModel[];
  messages: ChatMessageModel[];
  hasCollapsedMessages: boolean;
  isSubmitting: boolean;
  unreadCount: number;
  showScrollButton: boolean;
  chatInput: string;
  attachments: ChatAttachmentSummary[];
  composerResetSignal: number;
  chatScrollRef: RefObject<HTMLDivElement | null>;
  onLoadOlderMessages: () => void;
  onActionClick: (action: IADevAction) => void;
  onSubmit: () => void;
  onInputChange: (value: string) => void;
  onFilesAdded: (files: File[]) => void;
  onRemoveAttachment: (attachmentId: string) => void;
  onClearAttachments: () => void;
  onNavigateHistory: (direction: "up" | "down") => void;
  onUndo: () => void;
  onRedo: () => void;
  onScrollToBottomClick: () => void;
  onLoadDemo: () => void;
  onShowDashboard: (messageId: string) => void;
  onCopyMessage: (messageId: string) => void;
  onPrepareRelatedQuery: () => void;
};

const humanizeStatus = (
  taskPreparationLabel: string,
  chatStatus: string,
  streaming: boolean,
  attachmentCount: number,
) => {
  if (streaming) {
    const normalized = taskPreparationLabel.trim().toLowerCase();
    if (attachmentCount > 0) {
      return "Estoy revisando tu archivo...";
    }
    if (
      normalized.includes("valid") ||
      normalized.includes("buscando") ||
      normalized.includes("entendiendo")
    ) {
      return "Estoy revisando tu solicitud...";
    }
    if (normalized.includes("ejecut")) {
      return "Estoy procesando la informacion...";
    }
    return "Preparando una respuesta...";
  }

  const status = chatStatus.trim();
  if (!status) return "";
  if (
    status === "Listo para continuar." ||
    status === "Haz tu primera pregunta cuando quieras."
  ) {
    return "";
  }
  return status;
};

const ChatPanel = ({
  mode = "user",
  chatTitle,
  chatStatus,
  streaming,
  isWorkspaceLayout,
  activeDashboardMessageId,
  taskPreparationLabel,
  clarificationQuestion,
  visibleMessages,
  messages,
  hasCollapsedMessages,
  isSubmitting,
  unreadCount,
  showScrollButton,
  chatInput,
  attachments,
  composerResetSignal,
  chatScrollRef,
  onLoadOlderMessages,
  onActionClick,
  onSubmit,
  onInputChange,
  onFilesAdded,
  onRemoveAttachment,
  onClearAttachments,
  onNavigateHistory,
  onUndo,
  onRedo,
  onScrollToBottomClick,
  onLoadDemo,
  onShowDashboard,
  onCopyMessage,
  onPrepareRelatedQuery,
}: ChatPanelProps) => {
  const statusText =
    mode === "user"
      ? humanizeStatus(
          taskPreparationLabel,
          chatStatus,
          streaming,
          attachments.length,
        )
      : streaming
        ? taskPreparationLabel
        : chatStatus;

  const showWelcomeCard = visibleMessages.length <= 1 && mode === "user";

  return (
    <section className="relative flex h-full min-h-0 flex-col bg-[linear-gradient(180deg,var(--color-surface,#fff)_0%,var(--color-surface-subtle,#f8fafc)_100%)] dark:bg-[linear-gradient(180deg,#020617_0%,#0f172a_100%)]">
      <div className="border-b border-gray-200/80 px-4 py-3 backdrop-blur sm:px-5 dark:border-gray-800">
        <div className="flex flex-wrap items-center justify-end gap-2">
          {statusText ? (
            <div className="inline-flex min-w-0 items-center gap-2 rounded-full border border-gray-200 bg-white/85 px-3 py-1.5 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-900/85 dark:text-gray-300">
              <FileSearch size={13} className="shrink-0" />
              <span className="truncate">{statusText}</span>
            </div>
          ) : (
            <div className="hidden xl:block" aria-hidden="true" />
          )}
        </div>

        {mode === "dev" ? (
          <div className="mt-3">
            <p className="truncate text-base font-semibold text-gray-950 dark:text-white">
              {chatTitle}
            </p>
          </div>
        ) : null}

        {clarificationQuestion ? (
          <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
            <span className="font-semibold">Necesito una aclaracion:</span>{" "}
            {clarificationQuestion}
          </div>
        ) : null}
      </div>

      <div className="relative min-h-0 flex-1">
        <div ref={chatScrollRef} className="h-full overflow-auto px-4 py-5 sm:px-5">
          <div
            className={`w-full space-y-4 pb-6 ${
              isWorkspaceLayout ? "mx-auto max-w-5xl" : "mx-auto max-w-4xl"
            }`}
          >
            {showWelcomeCard ? (
              <div className="rounded-[28px] border border-gray-200/80 bg-white/90 px-5 py-5 text-sm text-gray-600 shadow-sm dark:border-gray-800 dark:bg-gray-900/70 dark:text-gray-300">
                <p>
                  Comparte una pregunta o adjunta un archivo para ayudarte con un
                  resumen, validacion o resultados accionables.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={onLoadDemo}
                    className="rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                  >
                    Ver ejemplo
                  </button>
                </div>
              </div>
            ) : null}

            {hasCollapsedMessages ? (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={onLoadOlderMessages}
                  className="rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                >
                  Cargar mensajes anteriores ({messages.length - visibleMessages.length})
                </button>
              </div>
            ) : null}

            <MessageList
              mode={mode}
              messages={visibleMessages}
              isBusy={isSubmitting}
              activeDashboardMessageId={activeDashboardMessageId}
              onActionClick={onActionClick}
              onShowDashboard={onShowDashboard}
              onCopyMessage={onCopyMessage}
              onPrepareRelatedQuery={onPrepareRelatedQuery}
            />
          </div>
        </div>

        {showScrollButton ? (
          <ScrollToBottomButton
            onClick={onScrollToBottomClick}
            unreadCount={unreadCount}
          />
        ) : null}
      </div>

      <MessageInput
        value={chatInput}
        attachments={attachments}
        disabled={isSubmitting}
        isGenerating={streaming}
        resetSignal={composerResetSignal}
        onChange={onInputChange}
        onFilesAdded={onFilesAdded}
        onRemoveAttachment={onRemoveAttachment}
        onClearAttachments={onClearAttachments}
        onSubmit={onSubmit}
        onNavigateHistory={onNavigateHistory}
        onUndo={onUndo}
        onRedo={onRedo}
      />
    </section>
  );
};

export default ChatPanel;
