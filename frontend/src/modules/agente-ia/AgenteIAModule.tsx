"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PageBreadcrumb from "@/components/common/PageBreadCrumb";
import type {
  ChatAttachmentSummary,
  ChatMessageModel,
} from "@/modules/programacion/ia-dev/chat/types";
import { mergeStreamingResponse } from "@/modules/programacion/ia-dev/chat/utils/mergeStreamingResponse";
import { normalizeChatPayload } from "@/modules/programacion/ia-dev/chat/utils/normalizeChatPayload";
import { usePromptHistory } from "@/modules/programacion/ia-dev/chat/hooks/usePromptHistory";
import { useSmartAutoScroll } from "@/modules/programacion/ia-dev/chat/hooks/useSmartAutoScroll";
import { useIADevChatTransport } from "@/modules/programacion/ia-dev/chat/hooks/useIADevChatTransport";
import {
  createIADevTicket,
  getIADevTaskStatus,
  type IADevAction,
  type IADevChatAttachment,
} from "@/services/ia-dev.service";
import ChatPanel from "@/modules/agente-ia/components/ChatPanel";
import DashboardPanel from "@/modules/agente-ia/components/DashboardPanel";
import SplitLayout from "@/modules/agente-ia/components/SplitLayout";
import { mockAnalyticsResponse } from "@/modules/agente-ia/mock/mockAnalyticsResponse";
import {
  clearAgenteIAChatHistory,
  loadAgenteIAChatHistory,
  saveAgenteIAChatHistory,
  type AgenteIAChatThread,
} from "@/modules/agente-ia/persistence/chatSessionStorage";
import {
  loadSplitViewState,
  saveSplitViewState,
} from "@/modules/agente-ia/persistence/splitViewStorage";
import {
  buildDashboardSnapshot,
  buildDashboardSnapshotFromMessage,
  getNormalizedPayload,
} from "@/modules/agente-ia/utils/buildDashboardSnapshot";
import HistoryPanel from "@/modules/agente-ia/components/HistoryPanel";

const INITIAL_ASSISTANT_MESSAGE =
  "Hola. Estoy listo para ayudarte con tu consulta.";
const INITIAL_CHAT_TIMESTAMP = "1970-01-01T00:00:00.000Z";
const MAX_CHAT_HISTORY = 30;

type ComposerAttachment = ChatAttachmentSummary & {
  file: File;
  lastModified: number;
};

const createMessageId = (role: "user" | "assistant") =>
  `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const createChatId = () =>
  `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const createAttachmentId = (file: File) =>
  `attachment-${file.name}-${file.size}-${file.lastModified}-${Math.random()
    .toString(36)
    .slice(2, 6)}`;

const inferAttachmentKind = (file: File): ChatAttachmentSummary["kind"] =>
  file.type.startsWith("image/") ? "image" : "document";

const toAttachmentSummary = (
  attachment: ComposerAttachment,
): ChatAttachmentSummary => ({
  id: attachment.id,
  name: attachment.name,
  mimeType: attachment.mimeType,
  size: attachment.size,
  kind: attachment.kind,
});

const fileToBase64 = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      const [, base64 = ""] = result.split(",", 2);
      if (!base64) {
        reject(new Error("attachment_base64_missing"));
        return;
      }
      resolve(base64);
    };
    reader.onerror = () => {
      reject(reader.error || new Error("attachment_read_failed"));
    };
    reader.readAsDataURL(file);
  });

const buildTransportAttachments = async (
  attachments: ComposerAttachment[],
): Promise<IADevChatAttachment[]> =>
  Promise.all(
    attachments.map(async (attachment) => ({
      id: attachment.id,
      name: attachment.name,
      mime_type: attachment.mimeType,
      size: attachment.size,
      kind: attachment.kind,
      last_modified: attachment.lastModified,
      content_base64: await fileToBase64(attachment.file),
    })),
  );

const INITIAL_MESSAGES: ChatMessageModel[] = [
  {
    id: "assistant-initial",
    role: "assistant",
    content: INITIAL_ASSISTANT_MESSAGE,
    createdAt: 0,
    status: "final",
  },
];

const getVisibleActions = (actions: IADevAction[] | undefined) =>
  (actions ?? []).filter((action) => action.type !== "memory_review");

const isOperationalChatStatus = (status: string) =>
  status.trim().toLowerCase() === "respuesta generada correctamente.";

const ACTIVE_BACKGROUND_STATUSES = new Set([
  "queued",
  "running",
  "resumed",
  "awaiting_approval",
  "paused",
]);

const DEFAULT_BACKGROUND_POLL_MS = 1000;
const BACKGROUND_POLL_ERROR_RETRY_MS = 5000;

const extractBackgroundRunId = (message: ChatMessageModel) => {
  const response = message.response;
  const background =
    response?.task?.current_run?.background ||
    (response?.task?.current_run?.final_state?.background_run_id
      ? { background_run_id: response.task.current_run.final_state.background_run_id }
      : null);
  const semantic = response?.task?.current_run?.semantic_explanation?.background_status;
  return (
    (typeof background?.background_run_id === "string"
      ? background.background_run_id
      : "") ||
    (typeof semantic?.background_run_id === "string"
      ? semantic.background_run_id
      : "")
  ).trim();
};

const extractBackgroundStatus = (message: ChatMessageModel) => {
  const status =
    message.response?.task?.current_run?.background?.run_status ||
    message.response?.task?.current_run?.status ||
    message.normalized?.semanticExplanation?.background_status?.status ||
    "";
  return String(status).trim().toLowerCase();
};

const extractBackgroundPollIntervalMs = (message: ChatMessageModel) => {
  const background = message.response?.task?.current_run?.background;
  const polling =
    (background?.polling as Record<string, unknown> | undefined) ||
    (message.response?.task?.current_run?.semantic_explanation?.background_status as
      | Record<string, unknown>
      | undefined);
  const candidates = [
    polling?.next_poll_after_ms,
    polling?.poll_interval_ms,
  ];
  for (const candidate of candidates) {
    const value =
      typeof candidate === "number"
        ? candidate
        : typeof candidate === "string"
          ? Number(candidate)
          : NaN;
    if (Number.isFinite(value) && value > 0) {
      return Math.max(1000, Math.min(value, 15000));
    }
  }
  return DEFAULT_BACKGROUND_POLL_MS;
};

const isPollableBackgroundMessage = (message: ChatMessageModel) =>
  message.role === "assistant" &&
  Boolean(extractBackgroundRunId(message)) &&
  ACTIVE_BACKGROUND_STATUSES.has(extractBackgroundStatus(message));

type PollableBackgroundTarget = {
  backgroundRunId: string;
  chatId: string;
  messageId: string;
  message: ChatMessageModel;
};

const collectPollableBackgroundTargets = (
  chat: AgenteIAChatThread | null,
): PollableBackgroundTarget[] => {
  const targetsByRunId = new Map<string, PollableBackgroundTarget>();
  if (!chat) return [];
  [...chat.messages]
    .reverse()
    .forEach((message) => {
      if (!isPollableBackgroundMessage(message)) return;
      const backgroundRunId = extractBackgroundRunId(message);
      if (!backgroundRunId || targetsByRunId.has(backgroundRunId)) return;
      targetsByRunId.set(backgroundRunId, {
        backgroundRunId,
        chatId: chat.id,
        messageId: message.id,
        message,
      });
    });
  return [...targetsByRunId.values()];
};

const getSuggestionQuery = (action: IADevAction) => {
  const payload = action.payload ?? {};
  const candidates = [
    payload.query,
    payload.message,
    payload.suggestion,
    payload.consulta,
    payload.prompt,
    action.label,
  ];

  return (
    candidates
      .map((candidate) =>
        typeof candidate === "string" ? candidate.trim() : "",
      )
      .find(Boolean) ?? ""
  );
};

const isKnownNonQueryAction = (action: IADevAction) =>
  action.type === "create_ticket" || action.type === "render_chart";

const chatHasUserMessages = (chat: AgenteIAChatThread) =>
  chat.messages.some(
    (message) => message.role === "user" && Boolean(message.content.trim()),
  );

const sortChatsByRecent = (chats: AgenteIAChatThread[]) =>
  [...chats].sort((left, right) => {
    const leftTime = Date.parse(left.updatedAt);
    const rightTime = Date.parse(right.updatedAt);
    return rightTime - leftTime;
  });

const buildChatTitle = (
  messages: ChatMessageModel[],
  fallbackPrompt?: string,
) => {
  const firstUserMessage = messages.find((message) => message.role === "user");
  const source = firstUserMessage?.content || fallbackPrompt || "";
  const compact = source.replace(/\s+/g, " ").trim();
  if (!compact) return "Nuevo chat";
  return compact.length > 52 ? `${compact.slice(0, 52)}...` : compact;
};

const buildChatPreview = (messages: ChatMessageModel[]) => {
  const meaningfulMessages = messages.filter(
    (message) =>
      message.content.trim() &&
      message.id !== "assistant-initial" &&
      message.content !== INITIAL_ASSISTANT_MESSAGE,
  );

  const latestMessage = meaningfulMessages[meaningfulMessages.length - 1];
  if (!latestMessage) return "Sin mensajes aun";

  const previewText =
    latestMessage.normalized?.summary || latestMessage.content || "";
  const compact = previewText.replace(/\s+/g, " ").trim();
  return compact.length > 86 ? `${compact.slice(0, 86)}...` : compact;
};

const buildBusinessReportText = (snapshot: ReturnType<typeof buildDashboardSnapshot>) => {
  const lines = [
    `Resumen ejecutivo: ${snapshot.executiveSummary}`,
    `Estado: ${snapshot.taskStatusLabel}`,
    `Dominio: ${snapshot.domain}`,
    `Intencion: ${snapshot.intent}`,
  ];

  if (snapshot.clarificationQuestion) {
    lines.push(`Aclaracion requerida: ${snapshot.clarificationQuestion}`);
  }

  if (snapshot.limitations.length > 0) {
    lines.push(`Limitaciones: ${snapshot.limitations.join(" | ")}`);
  }

  return lines.join("\n");
};

const createInitialChat = (): AgenteIAChatThread => ({
  id: "chat-inicial",
  title: "Nuevo chat",
  sessionId: null,
  chatStatus: "",
  messageWindowSize: 80,
  messages: INITIAL_MESSAGES,
  createdAt: INITIAL_CHAT_TIMESTAMP,
  updatedAt: INITIAL_CHAT_TIMESTAMP,
});

const createNewChat = (): AgenteIAChatThread => {
  const timestamp = new Date().toISOString();
  return {
    id: createChatId(),
    title: "Nuevo chat",
    sessionId: null,
    chatStatus: "",
    messageWindowSize: 80,
    messages: INITIAL_MESSAGES,
    createdAt: timestamp,
    updatedAt: timestamp,
  };
};

const AgenteIAModule = () => {
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const undoStackRef = useRef<string[]>([]);
  const redoStackRef = useRef<string[]>([]);

  const [initialHistoryState] = useState(() => {
    const persistedHistory = loadAgenteIAChatHistory();
    if (persistedHistory && persistedHistory.chats.length > 0) {
      const restoredChats = sortChatsByRecent(persistedHistory.chats);
      return {
        chats: restoredChats,
        activeChatId: persistedHistory.activeChatId ?? restoredChats[0]?.id ?? null,
        restoredFromHistory: true,
      };
    }

    const initialChat = createNewChat();
    return {
      chats: [initialChat],
      activeChatId: initialChat.id,
      restoredFromHistory: false,
    };
  });

  const [initialSplitViewState] = useState(() => loadSplitViewState());
  const { pushPrompt, navigate, resetNavigation } = usePromptHistory();
  const { sendMessage, lastError: transportError } = useIADevChatTransport();
  const {
    unreadCount,
    showScrollButton,
    notifyContentChanged,
    onScrollToBottomClick,
    scrollToBottom,
  } = useSmartAutoScroll({
    containerRef: chatScrollRef,
  });

  const [chatInput, setChatInput] = useState("");
  const [composerAttachments, setComposerAttachments] = useState<
    ComposerAttachment[]
  >([]);
  const [chats, setChats] = useState<AgenteIAChatThread[]>(
    initialHistoryState.chats,
  );
  const [activeChatId, setActiveChatId] = useState<string | null>(
    initialHistoryState.activeChatId,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(
    null,
  );
  const [composerResetSignal, setComposerResetSignal] = useState(0);
  const [historyCollapsed, setHistoryCollapsed] = useState(
    initialSplitViewState.historyCollapsed,
  );
  const [chatCollapsed, setChatCollapsed] = useState(
    initialSplitViewState.chatCollapsed,
  );
  const [dashboardCollapsed, setDashboardCollapsed] = useState(
    initialSplitViewState.dashboardCollapsed,
  );
  const [layoutSizes, setLayoutSizes] = useState(initialSplitViewState.sizes);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);
  const [dashboardDrawerOpen, setDashboardDrawerOpen] = useState(false);
  const [selectedDashboardMessageByChat, setSelectedDashboardMessageByChat] =
    useState(initialSplitViewState.selectedDashboardMessageByChat);

  const resolvedActiveChatId = useMemo(() => {
    if (activeChatId && chats.some((chat) => chat.id === activeChatId)) {
      return activeChatId;
    }
    return chats[0]?.id ?? null;
  }, [activeChatId, chats]);

  const activeChat = useMemo(
    () => chats.find((chat) => chat.id === resolvedActiveChatId) ?? null,
    [chats, resolvedActiveChatId],
  );
  const messages = activeChat?.messages ?? INITIAL_MESSAGES;
  const messageWindowSize = activeChat?.messageWindowSize ?? 80;
  const sessionId = activeChat?.sessionId ?? null;
  const chatStatus = activeChat?.chatStatus ?? "";
  const visibleMessages = useMemo(
    () => messages.slice(-messageWindowSize),
    [messageWindowSize, messages],
  );
  const hasCollapsedMessages = messages.length > messageWindowSize;
  const dashboardEntries = useMemo(() => {
    const assistantMessages = messages.filter(
      (message) => message.role === "assistant" && message.id !== "assistant-initial",
    );

    return assistantMessages.map((message, index) => {
      const snapshot = buildDashboardSnapshotFromMessage(message);
      const payload = getNormalizedPayload(message);
      const label = `Respuesta ${index + 1}`;
      const shortLabel = payload?.hasStructuredContent
        ? `${label} · dashboard`
        : `${label} · ${snapshot.lifecycleLabel.toLowerCase()}`;

      return {
        messageId: message.id,
        label,
        shortLabel,
        snapshot,
      };
    });
  }, [messages]);
  const latestDashboardEntry = dashboardEntries[dashboardEntries.length - 1] ?? null;
  const persistedSelectedDashboardMessageId = resolvedActiveChatId
    ? selectedDashboardMessageByChat[resolvedActiveChatId] ?? null
    : null;
  const resolvedSelectedDashboardMessageId = useMemo(() => {
    if (
      persistedSelectedDashboardMessageId &&
      dashboardEntries.some(
        (entry) => entry.messageId === persistedSelectedDashboardMessageId,
      )
    ) {
      return persistedSelectedDashboardMessageId;
    }

    return latestDashboardEntry?.messageId ?? null;
  }, [
    dashboardEntries,
    latestDashboardEntry?.messageId,
    persistedSelectedDashboardMessageId,
  ]);
  const dashboardSnapshot = useMemo(
    () => buildDashboardSnapshot(messages, resolvedSelectedDashboardMessageId),
    [messages, resolvedSelectedDashboardMessageId],
  );
  const liveDashboardSnapshot = latestDashboardEntry?.snapshot ?? null;
  const pollableBackgroundTargets = useMemo(
    () => collectPollableBackgroundTargets(activeChat),
    [activeChat],
  );

  const hasDashboardWorkspace = dashboardEntries.length > 0;

  const shouldUseWorkspaceLayout =
    hasDashboardWorkspace && messages.some((message) => message.role === "assistant");

  const effectiveChatStatus = useMemo(() => {
    if (transportError) {
      return "No fue posible conectar con el servicio en este momento.";
    }
    if (chatStatus && !isOperationalChatStatus(chatStatus)) {
      return chatStatus;
    }
    if (messages.length <= 1) {
      return "Haz tu primera pregunta cuando quieras.";
    }
    return "Listo para continuar.";
  }, [
    chatStatus,
    messages.length,
    transportError,
  ]);

  const historyDateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat("es-CO", {
        day: "2-digit",
        month: "short",
        hour: "numeric",
        minute: "2-digit",
      }),
    [],
  );

  const updateActiveChat = useCallback(
    (updater: (chat: AgenteIAChatThread) => AgenteIAChatThread) => {
      if (!resolvedActiveChatId) return;

      setChats((prev) =>
        sortChatsByRecent(
          prev.map((chat) =>
            chat.id === resolvedActiveChatId ? updater(chat) : chat,
          ),
        ).slice(0, MAX_CHAT_HISTORY),
      );
    },
    [resolvedActiveChatId],
  );

  const setActiveChatStatus = useCallback(
    (nextStatus: string) => {
      updateActiveChat((chat) => ({
        ...chat,
        chatStatus: nextStatus,
      }));
    },
    [updateActiveChat],
  );

  const backgroundPollersRef = useRef<
    Map<
      string,
      {
        cancel: () => void;
      }
    >
  >(new Map());

  useEffect(() => {
    const activeRunIds = new Set(
      pollableBackgroundTargets.map((target) => target.backgroundRunId),
    );
    backgroundPollersRef.current.forEach((poller, backgroundRunId) => {
      if (activeRunIds.has(backgroundRunId)) return;
      poller.cancel();
      backgroundPollersRef.current.delete(backgroundRunId);
    });

    pollableBackgroundTargets.forEach((target) => {
      if (backgroundPollersRef.current.has(target.backgroundRunId)) return;

      let cancelled = false;
      let inFlight = false;
      let timeoutId: number | null = null;
      let consecutiveErrors = 0;
      let activeController: AbortController | null = null;

      const cancel = () => {
        cancelled = true;
        activeController?.abort();
        if (timeoutId != null) {
          window.clearTimeout(timeoutId);
        }
      };

      const scheduleNext = (delayMs: number) => {
        if (cancelled) return;
        if (timeoutId != null) {
          window.clearTimeout(timeoutId);
        }
        timeoutId = window.setTimeout(() => {
          void poll();
        }, delayMs);
      };

      const poll = async () => {
        if (cancelled || inFlight) return;
        inFlight = true;
        const controller = new AbortController();
        activeController = controller;
        try {
          const result = await getIADevTaskStatus(
            {
              background_run_id: target.backgroundRunId,
            },
            {
              signal: controller.signal,
            },
          );
          if (cancelled) return;
          consecutiveErrors = 0;
          const normalizedPayload = normalizeChatPayload(result);
          const assistantReply = result.reply || result.task?.current_run.reply || "";
          const nextStatus = String(result.task?.current_run?.status || "")
            .trim()
            .toLowerCase();
          const nextDelay = extractBackgroundPollIntervalMs({
            ...target.message,
            response: result,
          });
          setChats((prev) =>
            sortChatsByRecent(
              prev.map((chat) =>
                chat.id !== target.chatId
                  ? chat
                  : {
                      ...chat,
                      chatStatus:
                        activeChatId === chat.id && consecutiveErrors > 0 ? "" : chat.chatStatus,
                      messages: chat.messages.map((message) =>
                        message.id === target.messageId
                          ? {
                              ...message,
                              content: assistantReply || message.content,
                              status: ACTIVE_BACKGROUND_STATUSES.has(nextStatus)
                                ? ("streaming" as const)
                                : ("final" as const),
                              response: result,
                              normalized: normalizedPayload,
                              error:
                                ACTIVE_BACKGROUND_STATUSES.has(nextStatus)
                                  ? undefined
                                  : message.error,
                            }
                          : message,
                      ),
                      updatedAt: new Date().toISOString(),
                    },
              ),
            ).slice(0, MAX_CHAT_HISTORY),
          );
          if (ACTIVE_BACKGROUND_STATUSES.has(nextStatus)) {
            scheduleNext(nextDelay);
            return;
          }
          backgroundPollersRef.current.get(target.backgroundRunId)?.cancel();
          backgroundPollersRef.current.delete(target.backgroundRunId);
        } catch {
          if (!cancelled) {
            consecutiveErrors += 1;
            if (activeChatId === target.chatId) {
              setChats((prev) =>
                prev.map((chat) =>
                  chat.id !== target.chatId
                    ? chat
                    : {
                        ...chat,
                        chatStatus:
                          consecutiveErrors >= 3
                            ? "Seguimos intentando reconectar con el job en background para mostrar el avance."
                            : "Reconectando con el job en background...",
                      },
                ),
              );
            }
            scheduleNext(BACKGROUND_POLL_ERROR_RETRY_MS);
          }
        } finally {
          activeController = null;
          inFlight = false;
        }
      };

      backgroundPollersRef.current.set(target.backgroundRunId, { cancel });
      void poll();
    });

  }, [activeChatId, pollableBackgroundTargets]);

  useEffect(
    () => () => {
      backgroundPollersRef.current.forEach((poller) => poller.cancel());
      backgroundPollersRef.current.clear();
    },
    [],
  );

  useEffect(() => {
    const persistableChats = chats.filter((chat) => chatHasUserMessages(chat));

    if (persistableChats.length === 0) {
      clearAgenteIAChatHistory();
      return;
    }

    const nextActiveChatId = persistableChats.some(
      (chat) => chat.id === activeChat?.id,
    )
      ? (activeChat?.id ?? null)
      : persistableChats[0].id;

    saveAgenteIAChatHistory({
      chats: persistableChats,
      activeChatId: nextActiveChatId,
    });
  }, [activeChat, chats]);

  useEffect(() => {
    if (!shouldUseWorkspaceLayout) return;

    saveSplitViewState({
      sizes: layoutSizes,
      historyCollapsed,
      chatCollapsed,
      dashboardCollapsed,
      selectedDashboardMessageByChat,
    });
  }, [
    chatCollapsed,
    dashboardCollapsed,
    historyCollapsed,
    layoutSizes,
    selectedDashboardMessageByChat,
    shouldUseWorkspaceLayout,
  ]);

  useEffect(() => {
    if (!resolvedActiveChatId) return;
    if (resolvedSelectedDashboardMessageId) return;
    if (!latestDashboardEntry) return;

    setSelectedDashboardMessageByChat((prev) => ({
      ...prev,
      [resolvedActiveChatId]: latestDashboardEntry.messageId,
    }));
  }, [
    latestDashboardEntry,
    resolvedActiveChatId,
    resolvedSelectedDashboardMessageId,
  ]);

  useEffect(() => {
    if (!activeChat?.id) return;

    const rafId = window.requestAnimationFrame(() => {
      scrollToBottom("auto");
    });

    return () => {
      window.cancelAnimationFrame(rafId);
    };
  }, [activeChat?.id, scrollToBottom]);

  const setChatInputTracked = (nextValue: string) => {
    setChatInput((prev) => {
      if (prev === nextValue) return prev;
      undoStackRef.current.push(prev);
      if (undoStackRef.current.length > 150) {
        undoStackRef.current.shift();
      }
      redoStackRef.current = [];
      return nextValue;
    });
  };

  const undoChatInput = () => {
    setChatInput((prev) => {
      if (undoStackRef.current.length === 0) return prev;
      const previous = undoStackRef.current.pop() ?? prev;
      redoStackRef.current.push(prev);
      return previous;
    });
  };

  const redoChatInput = () => {
    setChatInput((prev) => {
      if (redoStackRef.current.length === 0) return prev;
      const next = redoStackRef.current.pop() ?? prev;
      undoStackRef.current.push(prev);
      return next;
    });
  };

  const resetChatInputHistory = () => {
    undoStackRef.current = [];
    redoStackRef.current = [];
  };

  const clearComposerAttachments = useCallback(() => {
    setComposerAttachments([]);
  }, []);

  const removeComposerAttachment = useCallback((attachmentId: string) => {
    setComposerAttachments((prev) =>
      prev.filter((attachment) => attachment.id !== attachmentId),
    );
  }, []);

  const addComposerFiles = useCallback((files: File[]) => {
    setComposerAttachments((prev) => {
      const existingKeys = new Set(
        prev.map(
          (attachment) =>
            `${attachment.name}-${attachment.size}-${attachment.lastModified}`,
        ),
      );

      const nextAttachments = files.reduce<ComposerAttachment[]>(
        (accumulator, file) => {
          const dedupeKey = `${file.name}-${file.size}-${file.lastModified}`;
          if (existingKeys.has(dedupeKey)) {
            return accumulator;
          }

          existingKeys.add(dedupeKey);
          accumulator.push({
            id: createAttachmentId(file),
            name: file.name,
            mimeType: file.type || "application/octet-stream",
            size: file.size,
            kind: inferAttachmentKind(file),
            file,
            lastModified: file.lastModified,
          });
          return accumulator;
        },
        [],
      );

      return [...prev, ...nextAttachments];
    });
    setActiveChatStatus("Adjuntos listos para acompañar la consulta.");
  }, [setActiveChatStatus]);

  const resetComposerForChatChange = () => {
    setChatInput("");
    clearComposerAttachments();
    resetNavigation();
    resetChatInputHistory();
    setComposerResetSignal((prev) => prev + 1);
    setStreamingMessageId(null);
  };

  const appendAssistantMessage = (
    content: string,
    overrides?: Partial<ChatMessageModel>,
  ) => {
    updateActiveChat((chat) => {
      const nextMessages = [
        ...chat.messages,
        {
          id: createMessageId("assistant"),
          role: "assistant" as const,
          content,
          createdAt: Date.now(),
          status: "final" as const,
          ...overrides,
        },
      ];

      return {
        ...chat,
        messages: nextMessages,
        title: buildChatTitle(nextMessages),
        updatedAt: new Date().toISOString(),
      };
    });
    notifyContentChanged("new-message", { behavior: "smooth" });
  };

  const jumpToDashboard = useCallback(() => {
    if (!shouldUseWorkspaceLayout) return;
    setDashboardCollapsed(false);
    setChatCollapsed(false);
    setDashboardDrawerOpen(true);
    setHistoryDrawerOpen(false);
  }, [shouldUseWorkspaceLayout]);

  const selectDashboardMessage = useCallback(
    (messageId: string) => {
      if (!resolvedActiveChatId) return;

      setSelectedDashboardMessageByChat((prev) => ({
        ...prev,
        [resolvedActiveChatId]: messageId,
      }));
      jumpToDashboard();
    },
    [jumpToDashboard, resolvedActiveChatId],
  );

  const copyTextToClipboard = async (text: string, successStatus: string) => {
    const normalized = text.trim();
    if (!normalized || typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }

    try {
      await navigator.clipboard.writeText(normalized);
      setActiveChatStatus(successStatus);
    } catch {
      setActiveChatStatus("No fue posible copiar el contenido.");
    }
  };

  const prepareRelatedQuery = () => {
    const base = dashboardSnapshot.executiveSummary || dashboardSnapshot.summary;
    const prompt = `Quiero profundizar sobre esto: ${base}`;
    setChatInputTracked(prompt);
    setHistoryDrawerOpen(false);
    setDashboardDrawerOpen(false);
  };

  const copyAssistantMessageById = (messageId: string) => {
    const entry = dashboardEntries.find((item) => item.messageId === messageId);
    const text =
      entry?.snapshot.executiveSummary ||
      entry?.snapshot.summary ||
      messages.find((message) => message.id === messageId)?.content ||
      "";
    void copyTextToClipboard(text, "Respuesta copiada al portapapeles.");
  };

  const openChat = (chatId: string) => {
    if (isSubmitting || chatId === activeChatId) return;

    setActiveChatId(chatId);
    setHistoryCollapsed(false);
    setHistoryDrawerOpen(false);
    resetComposerForChatChange();
  };

  const startNewChat = () => {
    if (isSubmitting) return;
    if (activeChat && !chatHasUserMessages(activeChat)) {
      resetComposerForChatChange();
      setHistoryCollapsed(false);
      return;
    }

    const nextChat = createNewChat();
    setChats((prev) =>
      sortChatsByRecent([
        nextChat,
        ...prev.filter((chat) => chatHasUserMessages(chat)),
      ]).slice(0, MAX_CHAT_HISTORY),
    );
    setActiveChatId(nextChat.id);
    setHistoryCollapsed(false);
    setHistoryDrawerOpen(false);
    resetComposerForChatChange();
  };

  const renameChat = (chatId: string) => {
    const chat = chats.find((item) => item.id === chatId);
    if (!chat || typeof window === "undefined") return;

    const nextTitle = window.prompt("Nuevo nombre de la conversacion", chat.title);
    const normalizedTitle = nextTitle?.trim();
    if (!normalizedTitle) return;

    setChats((prev) =>
      prev.map((item) =>
        item.id === chatId
          ? { ...item, title: normalizedTitle, updatedAt: item.updatedAt }
          : item,
      ),
    );
  };

  const deleteChat = (chatId: string) => {
    const chat = chats.find((item) => item.id === chatId);
    if (!chat || typeof window === "undefined") return;
    const confirmed = window.confirm(
      `Se borrara la conversacion "${chat.title}". Esta accion solo afecta la persistencia local.`,
    );
    if (!confirmed) return;

    setChats((prev) => {
      const remaining = prev.filter((item) => item.id !== chatId);
      if (remaining.length > 0) {
        if (resolvedActiveChatId === chatId) {
          setActiveChatId(remaining[0].id);
          resetComposerForChatChange();
        }
        return remaining;
      }

      const nextChat = createNewChat();
      setActiveChatId(nextChat.id);
      resetComposerForChatChange();
      return [nextChat];
    });
  };

  const formatChatTimestamp = (chat: AgenteIAChatThread) => {
    if (chat.updatedAt === INITIAL_CHAT_TIMESTAMP) {
      return "Sin actividad";
    }

    return historyDateFormatter.format(new Date(chat.updatedAt));
  };

  const appendMockDemo = () => {
    if (!activeChat || isSubmitting) return;

    const userMessageId = createMessageId("user");
    const assistantMessageId = createMessageId("assistant");
    const prompt =
      "Muestrame un ejemplo de dashboard para materiales criticos por empleado.";
    const normalizedPayload = normalizeChatPayload(mockAnalyticsResponse);
    const submittedAt = new Date().toISOString();

    updateActiveChat((chat) => {
      const nextMessages = [
        ...chat.messages,
        {
          id: userMessageId,
          role: "user" as const,
          content: prompt,
          createdAt: Date.now(),
          status: "final" as const,
        },
        {
          id: assistantMessageId,
          role: "assistant" as const,
          content: mockAnalyticsResponse.reply,
          createdAt: Date.now(),
          status: "final" as const,
          response: mockAnalyticsResponse,
          normalized: normalizedPayload,
          actions: [],
          memoryCandidates: [],
          pendingProposals: [],
        },
      ];

      return {
        ...chat,
        sessionId: mockAnalyticsResponse.session_id,
        chatStatus: "Demo local cargada",
        messages: nextMessages,
        title: buildChatTitle(nextMessages, prompt),
        updatedAt: submittedAt,
      };
    });

    notifyContentChanged("new-message", { behavior: "smooth", force: true });
    if (resolvedActiveChatId) {
      setSelectedDashboardMessageByChat((prev) => ({
        ...prev,
        [resolvedActiveChatId]: assistantMessageId,
      }));
    }
  };

  const submitChat = async (overridePrompt?: string) => {
    const value = (overridePrompt ?? chatInput).trim();
    if (!value || isSubmitting || !activeChat) return;

    setIsSubmitting(true);

    const userMessageId = createMessageId("user");
    const assistantMessageId = createMessageId("assistant");
    const submittedAt = new Date().toISOString();
    const attachmentsForSubmission = composerAttachments.map((attachment) => ({
      ...attachment,
    }));
    const userMessageAttachments = attachmentsForSubmission.map((attachment) =>
      toAttachmentSummary(attachment),
    );
    let transportAttachments: IADevChatAttachment[] = [];

    try {
      transportAttachments = await buildTransportAttachments(
        attachmentsForSubmission,
      );
    } catch {
      setIsSubmitting(false);
      setActiveChatStatus(
        "No fue posible preparar los adjuntos para enviarlos.",
      );
      return;
    }

    updateActiveChat((chat) => {
      const nextMessages = [
        ...chat.messages,
        {
          id: userMessageId,
          role: "user" as const,
          content: value,
          createdAt: Date.now(),
          status: "final" as const,
          attachments: userMessageAttachments,
        },
        {
          id: assistantMessageId,
          role: "assistant" as const,
          content: "",
          createdAt: Date.now(),
          status: "streaming" as const,
        },
      ];

      return {
        ...chat,
        messages: nextMessages,
        title: buildChatTitle(nextMessages, value),
        updatedAt: submittedAt,
      };
    });
    setChatInput("");
    clearComposerAttachments();
    setComposerResetSignal((prev) => prev + 1);
    resetChatInputHistory();
    pushPrompt(value);
    resetNavigation();
    setStreamingMessageId(assistantMessageId);
    setHistoryCollapsed(false);
    notifyContentChanged("user-submit", { behavior: "smooth", force: true });

    try {
      const result = await sendMessage({
        message: value,
        sessionId: sessionId ?? undefined,
        attachments: transportAttachments,
        callbacks: {
          onStart: () => {
            notifyContentChanged("stream-start", { behavior: "smooth" });
          },
          onProgress: (progress) => {
            updateActiveChat((chat) => ({
              ...chat,
              messages: chat.messages.map((message) =>
                message.id === assistantMessageId
                  ? {
                      ...message,
                      response: mergeStreamingResponse(
                        message.response,
                        progress,
                      ),
                      status: "streaming",
                    }
                  : message,
              ),
              updatedAt: new Date().toISOString(),
            }));
            notifyContentChanged("stream-chunk", { behavior: "auto" });
          },
          onChunk: (chunk) => {
            if (!chunk) return;

            updateActiveChat((chat) => ({
              ...chat,
              messages: chat.messages.map((message) =>
                message.id === assistantMessageId
                  ? {
                      ...message,
                      content: `${message.content}${chunk}`,
                      status: "streaming",
                    }
                  : message,
              ),
              updatedAt: new Date().toISOString(),
            }));
            notifyContentChanged("stream-chunk", { behavior: "auto" });
          },
        },
      });

      const normalizedPayload = normalizeChatPayload(result);
      const visibleActions = getVisibleActions(result.actions);
      const assistantReply = result.reply || result.task?.current_run.reply || "";
      const nextStatus = String(
        result.task?.current_run?.background?.run_status ||
          result.task?.current_run?.status ||
          "",
      )
        .trim()
        .toLowerCase();

      updateActiveChat((chat) => {
        const nextMessages = chat.messages.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: assistantReply || message.content,
                status: ACTIVE_BACKGROUND_STATUSES.has(nextStatus)
                  ? ("streaming" as const)
                  : ("final" as const),
                response: result,
                normalized: normalizedPayload,
                actions: visibleActions,
                memoryCandidates: result.memory_candidates ?? [],
                pendingProposals: result.pending_proposals ?? [],
              }
            : message,
        );

        return {
          ...chat,
          sessionId: result.session_id,
          chatStatus: "",
          messages: nextMessages,
          title: buildChatTitle(nextMessages, value),
          updatedAt: new Date().toISOString(),
        };
      });
      notifyContentChanged("stream-end", { behavior: "smooth" });
    } catch (error) {
      const detail =
        typeof error === "object" &&
        error &&
        "detail" in error &&
        typeof (error as { detail?: unknown }).detail === "string"
          ? (error as { detail: string }).detail
          : typeof error === "object" &&
              error &&
              "message" in error &&
              typeof (error as { message?: unknown }).message === "string"
            ? (error as { message: string }).message
            : "No fue posible procesar la consulta con Agente IA.";

      updateActiveChat((chat) => ({
        ...chat,
        chatStatus: "Error de conexion con Agente IA",
        messages: chat.messages.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                status: "error" as const,
                content: `Error de integracion Agente IA: ${detail}`,
                error: detail,
              }
            : message,
        ),
        updatedAt: new Date().toISOString(),
      }));
    } finally {
      setStreamingMessageId(null);
      setIsSubmitting(false);
    }
  };

  const handleActionClick = async (action: IADevAction) => {
    if (isSubmitting) return;
    if (action.type === "render_chart") {
      updateActiveChat((chat) => ({
        ...chat,
        chatStatus: "La visualizacion ya se muestra en el panel derecho.",
      }));
      setDashboardDrawerOpen(true);
      return;
    }
    if (!isKnownNonQueryAction(action)) {
      const query = getSuggestionQuery(action);
      if (!query) return;
      await submitChat(query);
      return;
    }
    if (action.type !== "create_ticket") return;

    const title = action.payload?.title?.trim() || "Solicitud desde Agente IA";
    const description =
      action.payload?.description?.trim() ||
      "Solicitud generada desde interaccion Agente IA.";
    const category = action.payload?.category?.trim() || "general";

    try {
      setIsSubmitting(true);
      const created = await createIADevTicket({
        session_id: sessionId ?? undefined,
        title,
        description,
        category,
      });

      appendAssistantMessage(
        `Ticket creado correctamente: ${created.ticket.ticket_id}. El equipo de desarrollo puede tomarlo desde ahora.`,
      );
      updateActiveChat((chat) => ({
        ...chat,
        chatStatus: `Ticket ${created.ticket.ticket_id} creado`,
      }));
    } catch {
      appendAssistantMessage("No fue posible crear el ticket en este momento.", {
        status: "error",
      });
      updateActiveChat((chat) => ({
        ...chat,
        chatStatus: "Error al crear ticket",
      }));
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedDashboardIndex = dashboardEntries.findIndex(
    (entry) => entry.messageId === resolvedSelectedDashboardMessageId,
  );
  const canSelectPreviousDashboard = selectedDashboardIndex > 0;
  const canSelectNextDashboard =
    selectedDashboardIndex >= 0 &&
    selectedDashboardIndex < dashboardEntries.length - 1;
  const selectedDashboardLabel =
    dashboardEntries.find(
      (entry) => entry.messageId === resolvedSelectedDashboardMessageId,
    )?.label || "Consulta actual";

  return (
    <div className="w-full min-w-0 overflow-hidden">
      <PageBreadcrumb pageTitle={["Agente IA"]} />

      <div className="h-[calc(100vh-190px)] min-h-180 w-full min-w-0">
        <div className="h-full w-full min-w-0 px-1 md:px-2 xl:px-3">
          <section className="h-full overflow-hidden rounded-[32px] border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-950">
            <SplitLayout
              hasDashboard={shouldUseWorkspaceLayout}
              sizes={layoutSizes}
              historyCollapsed={historyCollapsed}
              chatCollapsed={chatCollapsed}
              dashboardCollapsed={dashboardCollapsed}
              historyDrawerOpen={historyDrawerOpen}
              dashboardDrawerOpen={dashboardDrawerOpen}
              onSizesChange={setLayoutSizes}
              onToggleHistory={() => setHistoryCollapsed((prev) => !prev)}
              onToggleChat={() => setChatCollapsed((prev) => !prev)}
              onToggleDashboard={() => setDashboardCollapsed((prev) => !prev)}
              onOpenHistoryDrawer={() => {
                setHistoryDrawerOpen(true);
                setDashboardDrawerOpen(false);
              }}
              onCloseHistoryDrawer={() => setHistoryDrawerOpen(false)}
              onOpenDashboardDrawer={() => {
                if (!shouldUseWorkspaceLayout) return;
                setDashboardDrawerOpen(true);
                setHistoryDrawerOpen(false);
              }}
              onCloseDashboardDrawer={() => setDashboardDrawerOpen(false)}
              historyToggleLabel="Historial"
              dashboardToggleLabel="Resultados"
              historyDrawerTitle="Historial"
              historyDrawerDescription="Conversaciones recientes"
              dashboardDrawerTitle="Resultados"
              dashboardDrawerDescription="Resumen, tablas y hallazgos relacionados"
              history={
                <HistoryPanel
                  threads={chats.filter((chat) => chatHasUserMessages(chat))}
                  activeChatId={resolvedActiveChatId}
                  isSubmitting={isSubmitting}
                  onOpenChat={openChat}
                  onStartNewChat={startNewChat}
                  onRenameChat={renameChat}
                  onDeleteChat={deleteChat}
                  formatChatTimestamp={formatChatTimestamp}
                  buildChatPreview={buildChatPreview}
                />
              }
              chat={
                <ChatPanel
                  mode="user"
                  chatTitle={activeChat?.title || "Nuevo chat"}
                  chatStatus={effectiveChatStatus}
                  streaming={Boolean(streamingMessageId)}
                  isWorkspaceLayout={shouldUseWorkspaceLayout}
                  activeDashboardMessageId={resolvedSelectedDashboardMessageId}
                  taskPreparationLabel={dashboardSnapshot.taskPreparationLabel}
                  clarificationQuestion={dashboardSnapshot.clarificationQuestion}
                  visibleMessages={visibleMessages}
                  messages={messages}
                  hasCollapsedMessages={hasCollapsedMessages}
                  isSubmitting={isSubmitting}
                  unreadCount={unreadCount}
                  showScrollButton={showScrollButton}
                  chatInput={chatInput}
                  attachments={composerAttachments.map((attachment) =>
                    toAttachmentSummary(attachment),
                  )}
                  composerResetSignal={composerResetSignal}
                  chatScrollRef={chatScrollRef}
                  onLoadOlderMessages={() =>
                    updateActiveChat((chat) => ({
                      ...chat,
                      messageWindowSize: Math.min(
                        chat.messages.length,
                        chat.messageWindowSize + 80,
                      ),
                    }))
                  }
                  onActionClick={(action) => {
                    void handleActionClick(action);
                  }}
                  onSubmit={() => {
                    void submitChat();
                  }}
                  onInputChange={setChatInputTracked}
                  onFilesAdded={addComposerFiles}
                  onRemoveAttachment={removeComposerAttachment}
                  onClearAttachments={clearComposerAttachments}
                  onNavigateHistory={(direction) => {
                    setChatInputTracked(navigate(direction, chatInput));
                  }}
                  onUndo={undoChatInput}
                  onRedo={redoChatInput}
                  onScrollToBottomClick={onScrollToBottomClick}
                  onLoadDemo={appendMockDemo}
                  onShowDashboard={selectDashboardMessage}
                  onCopyMessage={copyAssistantMessageById}
                  onPrepareRelatedQuery={prepareRelatedQuery}
                />
              }
              dashboard={
                <DashboardPanel
                  mode="user"
                  snapshot={dashboardSnapshot}
                  liveSnapshot={liveDashboardSnapshot}
                  historyEntries={dashboardEntries.map((entry) => ({
                    messageId: entry.messageId,
                    label: entry.label,
                    shortLabel: entry.shortLabel,
                  }))}
                  selectedMessageId={resolvedSelectedDashboardMessageId}
                  selectedMessageLabel={selectedDashboardLabel}
                  canSelectPrevious={canSelectPreviousDashboard}
                  canSelectNext={canSelectNextDashboard}
                  onSelectPrevious={() => {
                    if (!canSelectPreviousDashboard) return;
                    selectDashboardMessage(
                      dashboardEntries[selectedDashboardIndex - 1].messageId,
                    );
                  }}
                  onSelectNext={() => {
                    if (!canSelectNextDashboard) return;
                    selectDashboardMessage(
                      dashboardEntries[selectedDashboardIndex + 1].messageId,
                    );
                  }}
                  onSelectMessage={selectDashboardMessage}
                  onLoadDemo={appendMockDemo}
                  onCopyReport={() => {
                    void copyTextToClipboard(
                      buildBusinessReportText(dashboardSnapshot),
                      "Informe copiado al portapapeles.",
                    );
                  }}
                />
              }
            />
          </section>
        </div>
      </div>
    </div>
  );
};

export default AgenteIAModule;
