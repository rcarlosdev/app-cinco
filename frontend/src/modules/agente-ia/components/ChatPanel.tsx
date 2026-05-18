"use client";

import type { RefObject } from "react";
import type { IADevAction } from "@/services/ia-dev.service";
import { Sparkles } from "lucide-react";
import type {
  ChatAttachmentSummary,
  ChatMessageModel,
} from "@/modules/programacion/ia-dev/chat/types";
import MessageInput from "@/modules/agente-ia/components/MessageInput";
import MessageList from "@/modules/agente-ia/components/MessageList";
import TaskStatusBadge from "@/modules/agente-ia/components/TaskStatusBadge";
import ScrollToBottomButton from "@/modules/programacion/ia-dev/chat/components/ScrollToBottomButton";
import type { DashboardTaskStatusTone } from "@/modules/agente-ia/types";

type ChatPanelProps = {
  chatTitle: string;
  chatStatus: string;
  streaming: boolean;
  isWorkspaceLayout: boolean;
  activeDashboardMessageId: string | null;
  taskStatusLabel: string;
  taskStatusTone: DashboardTaskStatusTone;
  taskPreparationLabel: string;
  semanticHint: string;
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
  onOpenDashboardPanel: () => void;
  onCopyMessage: (messageId: string) => void;
  onPrepareRelatedQuery: () => void;
};

const ChatPanel = ({
  chatTitle,
  chatStatus,
  streaming,
  isWorkspaceLayout,
  activeDashboardMessageId,
  taskStatusLabel,
  taskStatusTone,
  taskPreparationLabel,
  semanticHint,
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
  onOpenDashboardPanel,
  onCopyMessage,
  onPrepareRelatedQuery,
}: ChatPanelProps) => {
  return (
    <section className="relative flex h-full min-h-0 flex-col bg-white dark:bg-gray-950">
      <header className="border-b border-gray-200 px-5 py-4 dark:border-gray-800">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-950 dark:text-white">
              <Sparkles size={16} />
              Chat conversacional
            </div>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Conversa con la IA y deja que el panel derecho materialice el resultado.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <TaskStatusBadge label={taskStatusLabel} tone={taskStatusTone} />
            {isWorkspaceLayout ? (
              <button
                type="button"
                onClick={onOpenDashboardPanel}
                className="rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
              >
                Abrir panel operativo
              </button>
            ) : null}
          </div>
        </div>

        <div className="mt-3">
          <p className="truncate text-base font-semibold text-gray-950 dark:text-white">
            {chatTitle}
          </p>
          <p className="mt-1 truncate text-sm text-gray-500 dark:text-gray-400">
            {streaming ? taskPreparationLabel : chatStatus}
          </p>
        </div>

        {semanticHint ? (
          <div className="mt-3 rounded-2xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100">
            {semanticHint}
          </div>
        ) : null}

        {clarificationQuestion ? (
          <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
            <span className="font-semibold">Hace falta una precision:</span>{" "}
            {clarificationQuestion}
          </div>
        ) : null}
      </header>

      

      <div className="relative min-h-0 flex-1">
        <div ref={chatScrollRef} className="h-full overflow-auto px-5 py-5">
          <div
            className={`w-full space-y-4 pb-6 ${
              isWorkspaceLayout ? "max-w-none" : "mx-auto max-w-4xl"
            }`}
          >
            {visibleMessages.length <= 1 && (
              <div className="rounded-[28px] border border-dashed border-gray-300 bg-gray-50 px-5 py-5 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
                Prueba preguntas conversacionales y analiticas. Si quieres ver el layout sin depender del backend, puedes cargar una demo local del dashboard.
                <div className="mt-3">
                  <button
                    type="button"
                    onClick={onLoadDemo}
                    className="rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                  >
                    Cargar demo
                  </button>
                </div>
              </div>
            )}

            {hasCollapsedMessages && (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={onLoadOlderMessages}
                  className="rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                >
                  Cargar mensajes anteriores ({messages.length - visibleMessages.length})
                </button>
              </div>
            )}

            <MessageList
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

        {showScrollButton && (
          <ScrollToBottomButton
            onClick={onScrollToBottomClick}
            unreadCount={unreadCount}
          />
        )}
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
