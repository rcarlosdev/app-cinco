"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PageBreadcrumb from "@/components/common/PageBreadCrumb";
import { MessageSquare, Plus } from "lucide-react";
import ChatComposer from "@/modules/programacion/ia-dev/chat/components/ChatComposer";
import ChatMessageItem from "@/modules/programacion/ia-dev/chat/components/ChatMessage";
import ScrollToBottomButton from "@/modules/programacion/ia-dev/chat/components/ScrollToBottomButton";
import { type ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import { mergeStreamingResponse } from "@/modules/programacion/ia-dev/chat/utils/mergeStreamingResponse";
import { normalizeChatPayload } from "@/modules/programacion/ia-dev/chat/utils/normalizeChatPayload";
import { usePromptHistory } from "@/modules/programacion/ia-dev/chat/hooks/usePromptHistory";
import { useSmartAutoScroll } from "@/modules/programacion/ia-dev/chat/hooks/useSmartAutoScroll";
import { useIADevChatTransport } from "@/modules/programacion/ia-dev/chat/hooks/useIADevChatTransport";
import {
  createIADevTicket,
  type IADevAction,
} from "@/services/ia-dev.service";
import {
  clearAgenteIAChatHistory,
  loadAgenteIAChatHistory,
  saveAgenteIAChatHistory,
  type AgenteIAChatThread,
} from "@/modules/agente-ia/persistence/chatSessionStorage";

const INITIAL_ASSISTANT_MESSAGE =
  "Agente IA listo. Describe tu consulta para continuar por chat.";
const INITIAL_CHAT_TIMESTAMP = "1970-01-01T00:00:00.000Z";
const MAX_CHAT_HISTORY = 30;

const createMessageId = (role: "user" | "assistant") =>
  `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const createChatId = () =>
  `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

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

  const compact = latestMessage.content.replace(/\s+/g, " ").trim();
  return compact.length > 86 ? `${compact.slice(0, 86)}...` : compact;
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
      return {
        chats: sortChatsByRecent(persistedHistory.chats),
        activeChatId:
          persistedHistory.activeChatId ?? persistedHistory.chats[0]?.id ?? null,
        restoredFromHistory: true,
      };
    }

    const initialChat = createInitialChat();
    return {
      chats: [initialChat],
      activeChatId: initialChat.id,
      restoredFromHistory: false,
    };
  });
  const { pushPrompt, navigate, resetNavigation } = usePromptHistory();
  const {
    sendMessage,
    lastError: transportError,
  } = useIADevChatTransport();
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
  const effectiveChatStatus = useMemo(() => {
    if (transportError) {
      return "No fue posible conectar con el servicio en este momento.";
    }
    if (chatStatus) {
      return chatStatus;
    }
    if (messages.length <= 1) {
      return "Nuevo chat listo para consultas.";
    }
    if (initialHistoryState.restoredFromHistory) {
      return "Historial recuperado correctamente.";
    }
    return "Listo para consultas analiticas.";
  }, [
    chatStatus,
    initialHistoryState.restoredFromHistory,
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

  useEffect(() => {
    const persistableChats = chats.filter((chat) => chatHasUserMessages(chat));

    if (persistableChats.length === 0) {
      clearAgenteIAChatHistory();
      return;
    }

    const nextActiveChatId = persistableChats.some(
      (chat) => chat.id === activeChat?.id,
    )
      ? activeChat?.id ?? null
      : persistableChats[0].id;

    saveAgenteIAChatHistory({
      chats: persistableChats,
      activeChatId: nextActiveChatId,
    });
  }, [activeChat, chats]);

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

  const resetComposerForChatChange = () => {
    setChatInput("");
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

  const openChat = (chatId: string) => {
    if (isSubmitting || chatId === activeChatId) return;

    setActiveChatId(chatId);
    resetComposerForChatChange();
  };

  const startNewChat = () => {
    if (isSubmitting) return;
    if (activeChat && !chatHasUserMessages(activeChat)) {
      resetComposerForChatChange();
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
    resetComposerForChatChange();
  };

  const formatChatTimestamp = (chat: AgenteIAChatThread) => {
    if (chat.updatedAt === INITIAL_CHAT_TIMESTAMP) {
      return "Sin actividad";
    }

    return historyDateFormatter.format(new Date(chat.updatedAt));
  };

  const submitChat = async () => {
    const value = chatInput.trim();
    if (!value || isSubmitting || !activeChat) return;

    const userMessageId = createMessageId("user");
    const assistantMessageId = createMessageId("assistant");
    const submittedAt = new Date().toISOString();

    updateActiveChat((chat) => {
      const nextMessages = [
        ...chat.messages,
        {
          id: userMessageId,
          role: "user" as const,
          content: value,
          createdAt: Date.now(),
          status: "final" as const,
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
    setComposerResetSignal((prev) => prev + 1);
    resetChatInputHistory();
    pushPrompt(value);
    resetNavigation();
    setStreamingMessageId(assistantMessageId);
    notifyContentChanged("user-submit", { behavior: "smooth", force: true });

    try {
      setIsSubmitting(true);
      const result = await sendMessage({
        message: value,
        sessionId: sessionId ?? undefined,
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
                      response: mergeStreamingResponse(message.response, progress),
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

      updateActiveChat((chat) => {
        const nextMessages = chat.messages.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: result.reply || message.content,
                status: "final" as const,
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
          chatStatus: "Respuesta generada correctamente.",
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
        chatStatus: "La visualizacion ya se muestra integrada en la respuesta.",
      }));
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

  return (
    <div className="w-full min-w-0 overflow-hidden">
      <PageBreadcrumb pageTitle={["Agente IA"]} />

      <div className="h-[calc(100vh-190px)] min-h-[680px] w-full min-w-0">
        <div className="mx-auto h-full min-w-0 max-w-[1400px]">
          <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white lg:flex-row dark:border-gray-800 dark:bg-white/3">
            <aside className="flex w-full shrink-0 flex-col border-b border-gray-200 bg-gray-50/80 lg:h-full lg:w-80 lg:border-r lg:border-b-0 dark:border-gray-800 dark:bg-gray-900/60">
              <div className="border-b border-gray-200 px-4 py-4 dark:border-gray-800">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-800 dark:text-white/90">
                      Historico de chats
                    </p>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-300">
                      Retoma conversaciones anteriores o inicia una nueva.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={startNewChat}
                    disabled={isSubmitting}
                    className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-500 text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-70"
                    title="Nuevo chat"
                  >
                    <Plus size={18} />
                  </button>
                </div>
              </div>

              <div className="border-b border-gray-200 px-4 py-2 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-300">
                {chats.length}{" "}
                {chats.length === 1 ? "conversacion" : "conversaciones"}
              </div>

              <div className="min-h-0 flex-1 overflow-auto p-3">
                <div className="space-y-2">
                  {chats.map((chat) => {
                    const isActive = chat.id === resolvedActiveChatId;

                    return (
                      <button
                        key={chat.id}
                        type="button"
                        onClick={() => openChat(chat.id)}
                        disabled={isSubmitting}
                        className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                          isActive
                            ? "border-brand-300 bg-brand-50 dark:border-brand-700 dark:bg-brand-500/10"
                            : "border-gray-200 bg-white hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-900 dark:hover:bg-gray-800/80"
                        } disabled:cursor-not-allowed disabled:opacity-70`}
                      >
                        <div className="flex items-start gap-3">
                          <span
                            className={`mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
                              isActive
                                ? "bg-brand-500 text-white"
                                : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
                            }`}
                          >
                            <MessageSquare size={16} />
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-start justify-between gap-2">
                              <p className="line-clamp-2 text-sm font-semibold text-gray-800 dark:text-white/90">
                                {chat.title}
                              </p>
                              <span className="shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
                                {formatChatTimestamp(chat)}
                              </span>
                            </div>
                            <p className="mt-1 line-clamp-2 text-xs text-gray-500 dark:text-gray-300">
                              {buildChatPreview(chat.messages)}
                            </p>
                            {chat.sessionId && (
                              <span className="mt-2 inline-flex rounded-full border border-gray-300 px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:border-gray-700 dark:text-gray-300">
                                Sesion activa
                              </span>
                            )}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </aside>

            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex items-start justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-gray-800">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-white/90">
                    <MessageSquare size={16} />
                    Agente Conversacional
                  </div>
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-300">
                    Modulo de chat para consultas analiticas con IA. Describe tu
                    consulta y el agente te respondera con insights,
                    visualizaciones y acciones recomendadas.
                  </p>
                </div>
              </div>

              <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-800">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-gray-800 dark:text-white/90">
                    {activeChat?.title || "Nuevo chat"}
                  </p>
                  <p className="mt-1 truncate text-sm text-gray-600 dark:text-gray-300">
                    {effectiveChatStatus}
                  </p>
                  {streamingMessageId && (
                    <p className="text-brand-600 dark:text-brand-300 mt-1 text-xs font-medium">
                      Agente escribiendo...
                    </p>
                  )}
                </div>
              </div>

              <div className="relative min-h-0 flex-1">
                <div ref={chatScrollRef} className="h-full overflow-auto p-4">
                  <div className="space-y-3">
                    {hasCollapsedMessages && (
                      <div className="flex justify-center">
                        <button
                          type="button"
                          onClick={() =>
                            updateActiveChat((chat) => ({
                              ...chat,
                              messageWindowSize: Math.min(
                                chat.messages.length,
                                chat.messageWindowSize + 80,
                              ),
                            }))
                          }
                          className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs font-semibold text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                        >
                          Cargar mensajes anteriores (
                          {messages.length - visibleMessages.length})
                        </button>
                      </div>
                    )}

                    {visibleMessages.map((message) => (
                      <ChatMessageItem
                        key={message.id}
                        message={message}
                        isBusy={isSubmitting}
                        onActionClick={(action) => {
                          void handleActionClick(action);
                        }}
                      />
                    ))}
                  </div>
                </div>

                {showScrollButton && (
                  <ScrollToBottomButton
                    onClick={onScrollToBottomClick}
                    unreadCount={unreadCount}
                  />
                )}
              </div>

              <ChatComposer
                value={chatInput}
                disabled={isSubmitting}
                isGenerating={Boolean(streamingMessageId)}
                resetSignal={composerResetSignal}
                onChange={setChatInputTracked}
                onSubmit={() => {
                  void submitChat();
                }}
                onNavigateHistory={(direction) => {
                  setChatInputTracked(navigate(direction, chatInput));
                }}
                onUndo={undoChatInput}
                onRedo={redoChatInput}
              />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default AgenteIAModule;
