"use client";

import { Pencil, Search, Trash2 } from "lucide-react";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import type { AgenteIAChatThread } from "@/modules/agente-ia/persistence/chatSessionStorage";

type ChatHistoryPanelProps = {
  search: string;
  threads: AgenteIAChatThread[];
  activeChatId: string | null;
  isSubmitting: boolean;
  onSearchChange: (value: string) => void;
  onOpenChat: (chatId: string) => void;
  onRenameChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  formatChatTimestamp: (chat: AgenteIAChatThread) => string;
  buildChatPreview: (messages: ChatMessageModel[]) => string;
};

const ChatHistoryPanel = ({
  search,
  threads,
  activeChatId,
  isSubmitting,
  onSearchChange,
  onOpenChat,
  onRenameChat,
  onDeleteChat,
  formatChatTimestamp,
  buildChatPreview,
}: ChatHistoryPanelProps) => {
  return (
    <div className="space-y-3">
      <label className="relative block">
        <Search
          size={14}
          className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-gray-400"
        />
        <input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Buscar conversacion"
          className="w-full rounded-2xl border border-gray-200 bg-gray-50 py-2 pr-3 pl-9 text-sm text-gray-700 outline-none transition focus:border-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
        />
      </label>

      <div className="space-y-2">
        {threads.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 px-4 py-5 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
            No hay conversaciones que coincidan con la busqueda.
          </div>
        ) : (
          threads.map((chat) => {
            const isActive = chat.id === activeChatId;

            return (
              <div
                key={chat.id}
                className={`rounded-2xl border transition ${
                  isActive
                    ? "border-[#111827] bg-gray-100 dark:border-white dark:bg-gray-900"
                    : "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950"
                }`}
              >
                <button
                  type="button"
                  onClick={() => onOpenChat(chat.id)}
                  className="w-full px-3 pt-3 text-left"
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

                <div className="flex items-center gap-2 px-3 pb-3">
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => onRenameChat(chat.id)}
                    className="inline-flex items-center gap-1 rounded-full border border-gray-200 px-2.5 py-1 text-[11px] text-gray-600 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
                  >
                    <Pencil size={11} />
                    Renombrar
                  </button>
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => onDeleteChat(chat.id)}
                    className="inline-flex items-center gap-1 rounded-full border border-red-200 px-2.5 py-1 text-[11px] text-red-600 transition hover:bg-red-50 disabled:opacity-50 dark:border-red-500/20 dark:text-red-300 dark:hover:bg-red-500/10"
                  >
                    <Trash2 size={11} />
                    Borrar
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default ChatHistoryPanel;
