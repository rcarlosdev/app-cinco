"use client";

import type { SplitLayoutSizes } from "@/modules/agente-ia/components/SplitLayout";

export type SplitViewState = {
  sizes: SplitLayoutSizes;
  activeTabletTab: "history" | "chat" | "dashboard";
  historyCollapsed: boolean;
  chatCollapsed: boolean;
  dashboardCollapsed: boolean;
};

const STORAGE_KEY = "agente-ia.split-view.v2";

const DEFAULT_STATE: SplitViewState = {
  sizes: {
    history: 15,
    chat: 30,
    dashboard: 55,
  },
  activeTabletTab: "chat",
  historyCollapsed: false,
  chatCollapsed: false,
  dashboardCollapsed: false,
};

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

const sanitizeSizes = (value: unknown): SplitLayoutSizes => {
  const source =
    value && typeof value === "object"
      ? (value as Partial<SplitLayoutSizes>)
      : {};

  return {
    history:
      typeof source.history === "number"
        ? clamp(source.history, 8, 35)
        : DEFAULT_STATE.sizes.history,
    chat:
      typeof source.chat === "number"
        ? clamp(source.chat, 18, 65)
        : DEFAULT_STATE.sizes.chat,
    dashboard:
      typeof source.dashboard === "number"
        ? clamp(source.dashboard, 20, 70)
        : DEFAULT_STATE.sizes.dashboard,
  };
};

export const loadSplitViewState = (): SplitViewState => {
  if (typeof window === "undefined") return DEFAULT_STATE;

  try {
    const parsed = JSON.parse(
      window.localStorage.getItem(STORAGE_KEY) || "null",
    ) as Partial<SplitViewState> | null;

    return {
      sizes: sanitizeSizes(parsed?.sizes),
      activeTabletTab:
        parsed?.activeTabletTab === "history" ||
        parsed?.activeTabletTab === "dashboard"
          ? parsed.activeTabletTab
          : "chat",
      historyCollapsed: Boolean(parsed?.historyCollapsed),
      chatCollapsed: Boolean(parsed?.chatCollapsed),
      dashboardCollapsed: Boolean(parsed?.dashboardCollapsed),
    };
  } catch {
    return DEFAULT_STATE;
  }
};

export const saveSplitViewState = (state: SplitViewState) => {
  if (typeof window === "undefined") return;

  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      sizes: sanitizeSizes(state.sizes),
      activeTabletTab: state.activeTabletTab,
      historyCollapsed: state.historyCollapsed,
      chatCollapsed: state.chatCollapsed,
      dashboardCollapsed: state.dashboardCollapsed,
    }),
  );
};