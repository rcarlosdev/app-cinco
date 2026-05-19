"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { LayoutPanelLeft, PanelRightOpen } from "lucide-react";
import PanelToggleButton from "@/modules/agente-ia/components/PanelToggleButton";
import ResponsiveDrawer from "@/modules/agente-ia/components/ResponsiveDrawer";

export type SplitLayoutSizes = {
  history: number;
  chat: number;
  dashboard: number;
};

type SplitLayoutProps = {
  hasDashboard: boolean;
  sizes: SplitLayoutSizes;
  historyCollapsed: boolean;
  chatCollapsed: boolean;
  dashboardCollapsed: boolean;
  historyDrawerOpen: boolean;
  dashboardDrawerOpen: boolean;
  onSizesChange: (sizes: SplitLayoutSizes) => void;
  onToggleHistory: () => void;
  onToggleChat: () => void;
  onToggleDashboard: () => void;
  onOpenHistoryDrawer: () => void;
  onCloseHistoryDrawer: () => void;
  onOpenDashboardDrawer: () => void;
  onCloseDashboardDrawer: () => void;
  historyToggleLabel?: string;
  dashboardToggleLabel?: string;
  historyDrawerTitle?: string;
  historyDrawerDescription?: string;
  dashboardDrawerTitle?: string;
  dashboardDrawerDescription?: string;
  history: ReactNode;
  chat: ReactNode;
  dashboard: ReactNode;
};

const MIN_PANEL = 12;
const COLLAPSED_PANEL_WIDTH = 52;
const RESIZE_HANDLE_WIDTH = 12;

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
  historyCollapsed,
  chatCollapsed,
  dashboardCollapsed,
  historyDrawerOpen,
  dashboardDrawerOpen,
  onSizesChange,
  onToggleHistory,
  onToggleChat,
  onToggleDashboard,
  onOpenHistoryDrawer,
  onCloseHistoryDrawer,
  onOpenDashboardDrawer,
  onCloseDashboardDrawer,
  historyToggleLabel = "Historial",
  dashboardToggleLabel = "Analisis",
  historyDrawerTitle = "Historial",
  historyDrawerDescription = "Tus conversaciones recientes",
  dashboardDrawerTitle = "Panel de analisis",
  dashboardDrawerDescription = "Detalle operativo y evidencia",
  history,
  chat,
  dashboard,
}: SplitLayoutProps) => {
  const desktopLayoutRef = useRef<HTMLDivElement>(null);
  const [dragMode, setDragMode] = useState<"history-chat" | "chat-dashboard" | null>(
    null,
  );

  const normalizedSizes = useMemo(() => normalizeSizes(sizes), [sizes]);

  useEffect(() => {
    if (!dragMode) return;

    const handlePointerMove = (event: PointerEvent) => {
      const containerRect = desktopLayoutRef.current?.getBoundingClientRect();
      const containerWidth = containerRect?.width ?? 0;
      if (!containerRect || !containerWidth) return;

      const x = ((event.clientX - containerRect.left) / containerWidth) * 100;
      const relativeX = Math.min(100, Math.max(0, x));

      if (dragMode === "history-chat") {
        const nextHistory = clamp(relativeX, 8, 35);
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
        const nextChat = clamp(relativeX - left, 18, 65);
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

  const historyBasis = normalizedSizes.history;
  const chatBasis = normalizedSizes.chat;
  const dashboardBasis = normalizedSizes.dashboard;

  const getPanelStyle = (basis: number, collapsed: boolean) =>
    collapsed
      ? ({
          flex: `0 0 ${COLLAPSED_PANEL_WIDTH}px`,
        } as const)
      : ({
          flexBasis: 0,
          flexGrow: basis,
          flexShrink: 1,
        } as const);

  return (
    <>
      <div ref={desktopLayoutRef} className="hidden h-full min-h-0 xl:flex">
        <div
          className="min-h-0 min-w-0 overflow-hidden"
          style={getPanelStyle(historyBasis, historyCollapsed)}
        >
          {historyCollapsed ? (
            <CollapsedRail label={historyToggleLabel} onClick={onToggleHistory} />
          ) : (
            history
          )}
        </div>

        <ResizeHandle onPointerDown={() => setDragMode("history-chat")} />

        <div
          className="min-h-0 min-w-0 overflow-hidden"
          style={getPanelStyle(chatBasis, chatCollapsed)}
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
          style={getPanelStyle(dashboardBasis, dashboardCollapsed)}
        >
          {dashboardCollapsed ? (
            <CollapsedRail label={dashboardToggleLabel} onClick={onToggleDashboard} />
          ) : (
            dashboard
          )}
        </div>
      </div>

      <div className="flex h-full min-h-0 flex-col xl:hidden">
        <div className="border-b border-gray-200 bg-white/92 px-4 py-3 backdrop-blur dark:border-gray-800 dark:bg-gray-950/92">
          <div className="flex flex-wrap items-center gap-2">
            <PanelToggleButton
              label={historyToggleLabel}
              ariaLabel="Abrir historial"
              onClick={onOpenHistoryDrawer}
              active={historyDrawerOpen}
            >
              <LayoutPanelLeft size={14} />
            </PanelToggleButton>
            {hasDashboard ? (
              <PanelToggleButton
                label={dashboardToggleLabel}
                ariaLabel={`Abrir ${dashboardDrawerTitle.toLowerCase()}`}
                onClick={onOpenDashboardDrawer}
                active={dashboardDrawerOpen}
              >
                <PanelRightOpen size={14} />
              </PanelToggleButton>
            ) : null}
          </div>
        </div>

        <div className="relative min-h-0 flex-1">
          <div className="h-full min-h-0">{chat}</div>
          <ResponsiveDrawer
            open={historyDrawerOpen}
            side="left"
            title={historyDrawerTitle}
            description={historyDrawerDescription}
            onClose={onCloseHistoryDrawer}
          >
            {history}
          </ResponsiveDrawer>
          {hasDashboard ? (
            <ResponsiveDrawer
              open={dashboardDrawerOpen}
              side="right"
              title={dashboardDrawerTitle}
              description={dashboardDrawerDescription}
              onClose={onCloseDashboardDrawer}
            >
              {dashboard}
            </ResponsiveDrawer>
          ) : null}
        </div>
      </div>
    </>
  );
};

const ResizeHandle = ({ onPointerDown }: { onPointerDown: () => void }) => (
  <div
    className="flex shrink-0 items-center justify-center bg-transparent"
    style={{ width: `${RESIZE_HANDLE_WIDTH}px` }}
  >
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
