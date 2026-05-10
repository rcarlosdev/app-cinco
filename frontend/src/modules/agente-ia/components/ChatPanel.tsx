"use client";

import type { RefObject } from "react";
import type { IADevAction } from "@/services/ia-dev.service";
import { Sparkles } from "lucide-react";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import MessageInput from "@/modules/agente-ia/components/MessageInput";
import MessageList from "@/modules/agente-ia/components/MessageList";
import ScrollToBottomButton from "@/modules/programacion/ia-dev/chat/components/ScrollToBottomButton";

type ChatPanelProps = {
  chatTitle: string;
  chatStatus: string;
  streaming: boolean;
  visibleMessages: ChatMessageModel[];
  messages: ChatMessageModel[];
  hasCollapsedMessages: boolean;
  isSubmitting: boolean;
  unreadCount: number;
  showScrollButton: boolean;
  chatInput: string;
  composerResetSignal: number;
  chatScrollRef: RefObject<HTMLDivElement | null>;
  onLoadOlderMessages: () => void;
  onActionClick: (action: IADevAction) => void;
  onSubmit: () => void;
  onInputChange: (value: string) => void;
  onNavigateHistory: (direction: "up" | "down") => void;
  onUndo: () => void;
  onRedo: () => void;
  onScrollToBottomClick: () => void;
  onLoadDemo: () => void;
};

const ChatPanel = ({
  chatTitle,
  chatStatus,
  streaming,
  visibleMessages,
  messages,
  hasCollapsedMessages,
  isSubmitting,
  unreadCount,
  showScrollButton,
  chatInput,
  composerResetSignal,
  chatScrollRef,
  onLoadOlderMessages,
  onActionClick,
  onSubmit,
  onInputChange,
  onNavigateHistory,
  onUndo,
  onRedo,
  onScrollToBottomClick,
  onLoadDemo,
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

          
        </div>

        <div className="mt-3">
          <p className="truncate text-base font-semibold text-gray-950 dark:text-white">
            {chatTitle}
          </p>
          <p className="mt-1 truncate text-sm text-gray-500 dark:text-gray-400">
            {streaming ? "Generando respuesta en streaming..." : chatStatus}
          </p>
        </div>
      </header>

      

      <div className="relative min-h-0 flex-1">
        <div ref={chatScrollRef} className="h-full overflow-auto px-5 py-5">
          <div className="mx-auto w-full max-w-3xl space-y-4 pb-6">
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
              onActionClick={onActionClick}
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
        disabled={isSubmitting}
        isGenerating={streaming}
        resetSignal={composerResetSignal}
        onChange={onInputChange}
        onSubmit={onSubmit}
        onNavigateHistory={onNavigateHistory}
        onUndo={onUndo}
        onRedo={onRedo}
      />
    </section>
  );
};

export default ChatPanel;
