"use client";

import { useMemo, useState } from "react";
import { MessageSquarePlus } from "lucide-react";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import ChatHistoryPanel from "@/modules/agente-ia/components/ChatHistoryPanel";
import type { AgenteIAChatThread } from "@/modules/agente-ia/persistence/chatSessionStorage";

type HistoryPanelProps = {
  threads: AgenteIAChatThread[];
  activeChatId: string | null;
  isSubmitting: boolean;
  onOpenChat: (chatId: string) => void;
  onStartNewChat: () => void;
  onRenameChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  formatChatTimestamp: (chat: AgenteIAChatThread) => string;
  buildChatPreview: (messages: ChatMessageModel[]) => string;
};

const HistoryPanel = ({
  threads,
  activeChatId,
  isSubmitting,
  onOpenChat,
  onStartNewChat,
  onRenameChat,
  onDeleteChat,
  formatChatTimestamp,
  buildChatPreview,
}: HistoryPanelProps) => {
  const [search, setSearch] = useState("");

  const filteredThreads = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return threads;

    return threads.filter((chat) => {
      const title = chat.title.toLowerCase();
      const preview = buildChatPreview(chat.messages).toLowerCase();
      return title.includes(query) || preview.includes(query);
    });
  }, [buildChatPreview, search, threads]);

  return (
    <aside className="flex h-full min-h-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <header className="border-b border-gray-200 px-4 py-4 dark:border-gray-800">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-gray-950 dark:text-white">
              Conversaciones
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Retoma conversaciones recientes o empieza una nueva.
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

      <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
        <ChatHistoryPanel
          search={search}
          threads={filteredThreads}
          activeChatId={activeChatId}
          isSubmitting={isSubmitting}
          onSearchChange={setSearch}
          onOpenChat={onOpenChat}
          onRenameChat={onRenameChat}
          onDeleteChat={onDeleteChat}
          formatChatTimestamp={formatChatTimestamp}
          buildChatPreview={buildChatPreview}
        />
      </div>
    </aside>
  );
};

export default HistoryPanel;
