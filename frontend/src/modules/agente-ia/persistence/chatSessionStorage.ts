"use client";

import type {
  ChatAttachmentSummary,
  ChatMessageModel,
  NormalizedAssistantPayload,
  NormalizedTable,
} from "@/modules/programacion/ia-dev/chat/types";

export type AgenteIAChatThread = {
  id: string;
  title: string;
  sessionId: string | null;
  chatStatus: string;
  messageWindowSize: number;
  messages: ChatMessageModel[];
  createdAt: string;
  updatedAt: string;
};

export type AgenteIAChatHistoryState = {
  version: 2;
  activeChatId: string | null;
  chats: AgenteIAChatThread[];
  updatedAt: string;
};

type LegacyChatSessionState = {
  version: 1;
  sessionId: string | null;
  chatStatus: string;
  messageWindowSize: number;
  messages: ChatMessageModel[];
  updatedAt: string;
};

const CHAT_HISTORY_KEY = "agente-ia.chat-history.v2";
const LEGACY_CHAT_SESSION_KEY = "agente-ia.chat-session.v1";
const MAX_PERSISTED_CHATS = 12;
const MAX_PERSISTED_MESSAGES_PER_CHAT = 40;
const MAX_PERSISTED_MESSAGE_CHARS = 12000;
const MAX_PERSISTED_INSIGHTS = 8;
const MAX_PERSISTED_TABLE_ROWS = 24;
const MAX_PERSISTED_EXTRA_TABLES = 2;
const MAX_PERSISTED_CHARTS = 2;

const safeParse = <T>(raw: string | null): T | null => {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
};

const sanitizeMessage = (message: ChatMessageModel): ChatMessageModel => {
  if (message.status !== "streaming") return message;

  const interruptedContent =
    message.content.trim() ||
    "La respuesta anterior se interrumpio antes de completarse.";

  return {
    ...message,
    status: "error",
    content: interruptedContent,
    error: message.error || "Respuesta interrumpida por recarga o cierre.",
  };
};

const sanitizeMessages = (messages: ChatMessageModel[] | undefined) =>
  Array.isArray(messages) ? messages.map((message) => sanitizeMessage(message)) : [];

const truncateText = (value: string, maxLength: number) => {
  const compact = value.trim();
  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, Math.max(0, maxLength - 3))}...`;
};

const sanitizeTableForStorage = (table: NormalizedTable | null): NormalizedTable | null => {
  if (!table) return null;

  const rows = table.rows.slice(0, MAX_PERSISTED_TABLE_ROWS);

  return {
    columns: table.columns,
    rows,
    exportRows: [],
    rowcount: table.rowcount,
    totalRecords: table.totalRecords,
    returnedRecords: Math.min(table.returnedRecords, rows.length),
    exportRecords: 0,
    exportTruncated: true,
    exportLimit: 0,
    truncated: table.truncated || table.rows.length > rows.length,
    limit: Math.min(table.limit || rows.length, rows.length),
  };
};

const sanitizeNormalizedForStorage = (
  payload: NormalizedAssistantPayload | null | undefined,
): NormalizedAssistantPayload | undefined => {
  if (!payload) return undefined;

  const insights = Array.isArray(payload.insights) ? payload.insights : [];
  const charts = Array.isArray(payload.charts) ? payload.charts : [];
  const extraTables = Array.isArray(payload.extraTables) ? payload.extraTables : [];
  const labels = Array.isArray(payload.labels) ? payload.labels : [];
  const series = Array.isArray(payload.series) ? payload.series : [];

  return {
    ...payload,
    summary: truncateText(payload.summary || "", 4000),
    insights: insights.slice(0, MAX_PERSISTED_INSIGHTS),
    charts: charts.slice(0, MAX_PERSISTED_CHARTS),
    chart: payload.chart ?? charts[0] ?? null,
    table: sanitizeTableForStorage(payload.table),
    extraTables: extraTables
      .slice(0, MAX_PERSISTED_EXTRA_TABLES)
      .map((table) => sanitizeTableForStorage(table))
      .filter((table): table is NormalizedTable => table != null),
    labels: labels.slice(0, MAX_PERSISTED_TABLE_ROWS),
    series: series.slice(0, MAX_PERSISTED_TABLE_ROWS),
    meta: {},
  };
};

const sanitizeAttachmentsForStorage = (
  attachments: ChatAttachmentSummary[] | undefined,
) =>
  Array.isArray(attachments)
    ? attachments.slice(0, 6).map((attachment) => ({
        id: attachment.id,
        name: truncateText(attachment.name, 180),
        mimeType: truncateText(attachment.mimeType || "", 120),
        size: attachment.size,
        kind: attachment.kind,
      }))
    : undefined;

const sanitizeMessageForStorage = (message: ChatMessageModel): ChatMessageModel => ({
  id: message.id,
  role: message.role,
  content: truncateText(message.content, MAX_PERSISTED_MESSAGE_CHARS),
  createdAt: message.createdAt,
  status: message.status,
  attachments: sanitizeAttachmentsForStorage(message.attachments),
  normalized: sanitizeNormalizedForStorage(message.normalized),
  actions: Array.isArray(message.actions) ? message.actions.slice(0, 6) : undefined,
  error: message.error ? truncateText(message.error, 1000) : undefined,
});

const sanitizeThreadForStorage = (thread: AgenteIAChatThread): AgenteIAChatThread =>
  sanitizeThread({
    ...thread,
    messages: thread.messages
      .slice(-MAX_PERSISTED_MESSAGES_PER_CHAT)
      .map((message) => sanitizeMessageForStorage(sanitizeMessage(message))),
  });

const isQuotaExceededError = (error: unknown) =>
  error instanceof DOMException &&
  (error.name === "QuotaExceededError" || error.name === "NS_ERROR_DOM_QUOTA_REACHED");

const tryPersistHistory = (payload: AgenteIAChatHistoryState) => {
  window.localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(payload));
};

const buildThreadTitle = (messages: ChatMessageModel[]) => {
  const firstUserMessage = messages.find((message) => message.role === "user");
  if (!firstUserMessage) return "Nuevo chat";

  const compact = firstUserMessage.content.replace(/\s+/g, " ").trim();
  if (!compact) return "Nuevo chat";
  return compact.length > 52 ? `${compact.slice(0, 52)}...` : compact;
};

const sanitizeThread = (thread: AgenteIAChatThread): AgenteIAChatThread => {
  const messages = sanitizeMessages(thread.messages);
  const updatedAt =
    typeof thread.updatedAt === "string"
      ? thread.updatedAt
      : new Date().toISOString();

  return {
    id: thread.id,
    title: typeof thread.title === "string" && thread.title.trim()
      ? thread.title
      : buildThreadTitle(messages),
    sessionId: thread.sessionId ?? null,
    chatStatus: typeof thread.chatStatus === "string" ? thread.chatStatus : "",
    messageWindowSize:
      typeof thread.messageWindowSize === "number" ? thread.messageWindowSize : 80,
    messages,
    createdAt:
      typeof thread.createdAt === "string" ? thread.createdAt : updatedAt,
    updatedAt,
  };
};

const migrateLegacySession = (): AgenteIAChatHistoryState | null => {
  const legacySession = safeParse<LegacyChatSessionState>(
    window.sessionStorage.getItem(LEGACY_CHAT_SESSION_KEY),
  );

  if (!legacySession || legacySession.version !== 1) return null;

  const updatedAt =
    typeof legacySession.updatedAt === "string"
      ? legacySession.updatedAt
      : new Date().toISOString();

  const migratedThread = sanitizeThread({
    id: "chat-inicial",
    title: buildThreadTitle(sanitizeMessages(legacySession.messages)),
    sessionId: legacySession.sessionId ?? null,
    chatStatus:
      typeof legacySession.chatStatus === "string" ? legacySession.chatStatus : "",
    messageWindowSize:
      typeof legacySession.messageWindowSize === "number"
        ? legacySession.messageWindowSize
        : 80,
    messages: sanitizeMessages(legacySession.messages),
    createdAt: updatedAt,
    updatedAt,
  });

  window.sessionStorage.removeItem(LEGACY_CHAT_SESSION_KEY);

  return {
    version: 2,
    activeChatId: migratedThread.id,
    chats: [migratedThread],
    updatedAt,
  };
};

export const loadAgenteIAChatHistory = (): AgenteIAChatHistoryState | null => {
  if (typeof window === "undefined") return null;

  const parsed = safeParse<AgenteIAChatHistoryState>(
    window.localStorage.getItem(CHAT_HISTORY_KEY),
  );

  if (parsed && parsed.version === 2) {
    const chats = Array.isArray(parsed.chats)
      ? parsed.chats.map((chat) => sanitizeThread(chat))
      : [];

    return {
      version: 2,
      activeChatId: parsed.activeChatId ?? chats[0]?.id ?? null,
      chats,
      updatedAt:
        typeof parsed.updatedAt === "string"
          ? parsed.updatedAt
          : new Date().toISOString(),
    };
  }

  return migrateLegacySession();
};

export const saveAgenteIAChatHistory = (
  state: Omit<AgenteIAChatHistoryState, "version" | "updatedAt">,
) => {
  if (typeof window === "undefined") return;

  const persistedChats = state.chats
    .map((chat) => sanitizeThreadForStorage(chat))
    .slice(0, MAX_PERSISTED_CHATS);
  const persistedActiveChatId = persistedChats.some(
    (chat) => chat.id === state.activeChatId,
  )
    ? state.activeChatId
    : persistedChats[0]?.id ?? null;

  const basePayload: AgenteIAChatHistoryState = {
    version: 2,
    activeChatId: persistedActiveChatId,
    chats: persistedChats,
    updatedAt: new Date().toISOString(),
  };

  try {
    tryPersistHistory(basePayload);
  } catch (error) {
    if (!isQuotaExceededError(error)) {
      throw error;
    }

    const lightweightPayload: AgenteIAChatHistoryState = {
      ...basePayload,
      chats: basePayload.chats.slice(0, 6).map((chat) => ({
        ...chat,
        messages: chat.messages.map((message) => ({
          id: message.id,
          role: message.role,
          content: truncateText(message.content, 2000),
          createdAt: message.createdAt,
          status: message.status,
          attachments: sanitizeAttachmentsForStorage(message.attachments),
          error: message.error,
        })),
      })),
    };
    lightweightPayload.activeChatId = lightweightPayload.chats.some(
      (chat) => chat.id === lightweightPayload.activeChatId,
    )
      ? lightweightPayload.activeChatId
      : lightweightPayload.chats[0]?.id ?? null;

    try {
      tryPersistHistory(lightweightPayload);
    } catch (fallbackError) {
      if (!isQuotaExceededError(fallbackError)) {
        throw fallbackError;
      }

      window.localStorage.removeItem(CHAT_HISTORY_KEY);
    }
  }
};

export const clearAgenteIAChatHistory = () => {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CHAT_HISTORY_KEY);
  window.sessionStorage.removeItem(LEGACY_CHAT_SESSION_KEY);
};
