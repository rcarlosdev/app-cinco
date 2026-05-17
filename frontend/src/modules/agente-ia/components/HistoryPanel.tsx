"use client";

import { useMemo, useState } from "react";
import { MessageSquarePlus } from "lucide-react";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import ChatHistoryPanel from "@/modules/agente-ia/components/ChatHistoryPanel";
import FeaturePanel from "@/modules/agente-ia/components/FeaturePanel";
import ToolsPanel from "@/modules/agente-ia/components/ToolsPanel";
import type { AgenteIAChatThread } from "@/modules/agente-ia/persistence/chatSessionStorage";
import type { DashboardSnapshot } from "@/modules/agente-ia/types";

type HistoryPanelProps = {
  threads: AgenteIAChatThread[];
  activeChatId: string | null;
  isSubmitting: boolean;
  snapshot: DashboardSnapshot;
  onOpenChat: (chatId: string) => void;
  onStartNewChat: () => void;
  onRenameChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  formatChatTimestamp: (chat: AgenteIAChatThread) => string;
  buildChatPreview: (messages: ChatMessageModel[]) => string;
};

const tabs = [
  { id: "history", label: "Historial" },
  { id: "tools", label: "Herramientas" },
  { id: "features", label: "Caracteristicas" },
] as const;

const HistoryPanel = ({
  threads,
  activeChatId,
  isSubmitting,
  snapshot,
  onOpenChat,
  onStartNewChat,
  onRenameChat,
  onDeleteChat,
  formatChatTimestamp,
  buildChatPreview,
}: HistoryPanelProps) => {
  const [activeTab, setActiveTab] =
    useState<(typeof tabs)[number]["id"]>("history");
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
              Soporte operativo
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Historial, capacidades y guia de uso.
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

        <div className="mt-4 inline-flex rounded-full border border-gray-300 p-1 dark:border-gray-700">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                activeTab === tab.id
                  ? "bg-[#111827] text-white"
                  : "text-gray-600 dark:text-gray-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
        {activeTab === "history" ? (
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
        ) : activeTab === "tools" ? (
          <ToolsPanel snapshot={snapshot} />
        ) : (
          <FeaturePanel />
        )}
      </div>
    </aside>
  );
};

export default HistoryPanel;
