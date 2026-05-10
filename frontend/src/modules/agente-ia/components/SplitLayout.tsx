"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

export type SplitLayoutSizes = {
  history: number;
  chat: number;
  dashboard: number;
};

type SplitLayoutProps = {
  hasDashboard: boolean;
  sizes: SplitLayoutSizes;
  activeTabletTab: "history" | "chat" | "dashboard";
  historyCollapsed: boolean;
  chatCollapsed: boolean;
  dashboardCollapsed: boolean;
  onSizesChange: (sizes: SplitLayoutSizes) => void;
  onTabletTabChange: (tab: "history" | "chat" | "dashboard") => void;
  onToggleHistory: () => void;
  onToggleChat: () => void;
  onToggleDashboard: () => void;
  history: ReactNode;
  chat: ReactNode;
  dashboard: ReactNode;
};

const MIN_PANEL = 12;
const COLLAPSED_WIDTH = 4;

const clamp = (value: number, min = MIN_PANEL, max = 80) =>
  Math.min(max, Math.max(min, value));

const normalizeSizes = (sizes: SplitLayoutSizes): SplitLayoutSizes => {
  const total = sizes.history + sizes.chat + sizes.dashboard || 100;

  return {
    history: (sizes.history / total) * 100,
    chat: (sizes.chat / total) * 100,
    dashboard: (sizes.dashboard / total) * 100,
  };
};

const SplitLayout = ({
  hasDashboard,
  sizes,
  activeTabletTab,
  historyCollapsed,
  chatCollapsed,
  dashboardCollapsed,
  onSizesChange,
  onTabletTabChange,
  onToggleHistory,
  onToggleChat,
  onToggleDashboard,
  history,
  chat,
  dashboard,
}: SplitLayoutProps) => {
  const [dragMode, setDragMode] = useState<"history-chat" | "chat-dashboard" | null>(
    null,
  );

  const normalizedSizes = useMemo(() => normalizeSizes(sizes), [sizes]);

  useEffect(() => {
    if (!dragMode) return;

    const handlePointerMove = (event: PointerEvent) => {
      const viewportWidth = window.innerWidth;
      if (!viewportWidth) return;

      const x = (event.clientX / viewportWidth) * 100;

      if (dragMode === "history-chat") {
        const nextHistory = clamp(x, 8, 35);
        const delta = nextHistory - normalizedSizes.history;
        const nextChat = clamp(normalizedSizes.chat - delta, 18, 60);

        onSizesChange(
          normalizeSizes({
            history: nextHistory,
            chat: nextChat,
            dashboard: normalizedSizes.dashboard,
          }),
        );
      }

      if (dragMode === "chat-dashboard") {
        const left = normalizedSizes.history;
        const nextChat = clamp(x - left, 18, 65);
        const nextDashboard = clamp(100 - left - nextChat, 20, 70);

        onSizesChange(
          normalizeSizes({
            history: normalizedSizes.history,
            chat: nextChat,
            dashboard: nextDashboard,
          }),
        );
      }
    };

    const handlePointerUp = () => setDragMode(null);

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [dragMode, normalizedSizes, onSizesChange]);

  if (!hasDashboard) {
    return (
      <div className="flex h-full min-h-0">
        <div className="min-h-0 min-w-0 flex-1">{chat}</div>
      </div>
    );
  }

  const historyBasis = historyCollapsed ? COLLAPSED_WIDTH : normalizedSizes.history;
  const chatBasis = chatCollapsed ? COLLAPSED_WIDTH : normalizedSizes.chat;
  const dashboardBasis = dashboardCollapsed
    ? COLLAPSED_WIDTH
    : normalizedSizes.dashboard;

  return (
    <>
      <div className="hidden h-full min-h-0 lg:flex">
        <div
          className="min-h-0 min-w-0 overflow-hidden"
          style={{ flexBasis: `${historyBasis}%` }}
        >
          {historyCollapsed ? (
            <CollapsedRail label="Historial" onClick={onToggleHistory} />
          ) : (
            history
          )}
        </div>

        <ResizeHandle onPointerDown={() => setDragMode("history-chat")} />

        <div
          className="min-h-0 min-w-0 overflow-hidden"
          style={{ flexBasis: `${chatBasis}%` }}
        >
          {chatCollapsed ? (
            <CollapsedRail label="Chat" onClick={onToggleChat} />
          ) : (
            chat
          )}
        </div>

        <ResizeHandle onPointerDown={() => setDragMode("chat-dashboard")} />

        <div
          className="min-h-0 min-w-0 overflow-hidden"
          style={{ flexBasis: `${dashboardBasis}%` }}
        >
          {dashboardCollapsed ? (
            <CollapsedRail label="Dashboard" onClick={onToggleDashboard} />
          ) : (
            dashboard
          )}
        </div>
      </div>

      <div className="hidden h-full min-h-0 md:flex lg:hidden">
        <div className="flex min-h-0 w-full flex-col">
          <div className="border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-950">
            <div className="inline-flex rounded-full border border-gray-300 p-1 dark:border-gray-700">
              {(["history", "chat", "dashboard"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => onTabletTabChange(tab)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    activeTabletTab === tab
                      ? "bg-[#111827] text-white"
                      : "text-gray-600 dark:text-gray-300"
                  }`}
                >
                  {tab === "history" ? "Historial" : tab === "chat" ? "Chat" : "Dashboard"}
                </button>
              ))}
            </div>
          </div>

          <div className="min-h-0 flex-1">
            {activeTabletTab === "history"
              ? history
              : activeTabletTab === "chat"
                ? chat
                : dashboard}
          </div>
        </div>
      </div>

      <div className="flex h-full min-h-0 flex-col md:hidden">
        {activeTabletTab === "history"
          ? history
          : activeTabletTab === "dashboard"
            ? dashboard
            : chat}
      </div>
    </>
  );
};

const ResizeHandle = ({ onPointerDown }: { onPointerDown: () => void }) => (
  <div className="flex w-3 shrink-0 items-center justify-center bg-transparent">
    <button
      type="button"
      aria-label="Redimensionar paneles"
      onPointerDown={onPointerDown}
      className="group flex h-full w-full cursor-col-resize items-center justify-center"
    >
      <span className="h-16 w-1 rounded-full bg-gray-300 transition group-hover:bg-gray-500 dark:bg-gray-700 dark:group-hover:bg-gray-500" />
    </button>
  </div>
);

const CollapsedRail = ({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="flex h-full w-full items-center justify-center border-x border-gray-200 bg-gray-50 text-xs font-semibold tracking-[0.16em] text-gray-500 uppercase dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400"
  >
    <span className="-rotate-90 whitespace-nowrap">{label}</span>
  </button>
);

export default SplitLayout;