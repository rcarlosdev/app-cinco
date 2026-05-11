"use client";

import { MessageSquarePlus } from "lucide-react";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import type { AgenteIAChatThread } from "@/modules/agente-ia/persistence/chatSessionStorage";

type HistoryPanelProps = {
  threads: AgenteIAChatThread[];
  activeChatId: string | null;
  isSubmitting: boolean;
  onOpenChat: (chatId: string) => void;
  onStartNewChat: () => void;
  formatChatTimestamp: (chat: AgenteIAChatThread) => string;
  buildChatPreview: (messages: ChatMessageModel[]) => string;
};

const HistoryPanel = ({
  threads,
  activeChatId,
  isSubmitting,
  onOpenChat,
  onStartNewChat,
  formatChatTimestamp,
  buildChatPreview,
}: HistoryPanelProps) => {
  return (
    <aside className="flex h-full min-h-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <header className="border-b border-gray-200 px-4 py-4 dark:border-gray-800">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-gray-950 dark:text-white">
              Chats
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {threads.length} conversaciones
            </p>
          </div>

          <button
            type="button"
            disabled={isSubmitting}
            onClick={onStartNewChat}
            className="inline-flex items-center gap-1 rounded-full bg-[#111827] px-3 py-2 text-xs font-medium text-white transition hover:bg-[#1f2937] disabled:opacity-50"
          >
            <MessageSquarePlus size={14} />
            Nuevo
          </button>
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-2 overflow-auto px-3 py-3">
        {threads.map((chat) => {
          const isActive = chat.id === activeChatId;

          return (
            <button
              key={chat.id}
              type="button"
              onClick={() => onOpenChat(chat.id)}
              className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                isActive
                  ? "border-[#111827] bg-gray-100 dark:border-white dark:bg-gray-900"
                  : "border-gray-200 bg-white hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:hover:bg-gray-900"
              }`}
            >
              <p className="line-clamp-2 text-sm font-semibold text-gray-900 dark:text-white">
                {chat.title}
              </p>
              <p className="mt-1 line-clamp-2 text-xs text-gray-500 dark:text-gray-400">
                {buildChatPreview(chat.messages)}
              </p>
              <p className="mt-2 text-[11px] text-gray-400">
                {formatChatTimestamp(chat)}
              </p>
            </button>
          );
        })}
      </div>
    </aside>
  );
};

export default HistoryPanel;