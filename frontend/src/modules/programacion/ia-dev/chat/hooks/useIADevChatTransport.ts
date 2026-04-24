import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL } from "@/lib/apiConfig";
import {
  sendIADevMessage,
  type IADevChatResponse,
} from "@/services/ia-dev.service";
import type { ChatSubmitStreamCallbacks } from "@/modules/programacion/ia-dev/chat/types";

type ConnectionState =
  | "disabled"
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed"
  | "error";

type SendMessageParams = {
  message: string;
  sessionId?: string | null;
  callbacks?: ChatSubmitStreamCallbacks;
};

type PendingRequest = {
  id: string;
  callbacks?: ChatSubmitStreamCallbacks;
  resolve: (value: IADevChatResponse) => void;
  reject: (reason?: unknown) => void;
  timeoutId: number;
};

type WebSocketEventPayload = {
  type?: string;
  request_id?: string;
  chunk?: string;
  delta?: string;
  content?: string;
  working_updates?: IADevChatResponse["working_updates"];
  reasoning?: IADevChatResponse["reasoning"];
  status_text?: string;
  response?: IADevChatResponse;
  data?: IADevChatResponse;
  error?: string;
  detail?: string;
  session_id?: string;
  reply?: string;
};

const MAX_WS_WAIT_MS = 180000;
const MAX_RECONNECT_DELAY_MS = 10000;

const buildDefaultWsUrl = (): string | null => {
  const configured = (process.env.NEXT_PUBLIC_IA_DEV_WS_URL || "").trim();
  if (configured) return configured;
  return null;
};

const chunkText = (text: string): string[] => {
  if (!text.trim()) return [];
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length <= 4) return [text];

  const chunkSize = Math.max(3, Math.ceil(words.length / 18));
  const chunks: string[] = [];
  for (let index = 0; index < words.length; index += chunkSize) {
    chunks.push(`${words.slice(index, index + chunkSize).join(" ")} `);
  }
  return chunks;
};

const streamChunks = async (
  text: string,
  onChunk?: (chunk: string) => void,
): Promise<void> => {
  if (!onChunk) return;
  const chunks = chunkText(text);
  for (const chunk of chunks) {
    onChunk(chunk);
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, 14);
    });
  }
};

const buildFallbackResponseFromEvent = (
  payload: WebSocketEventPayload,
): IADevChatResponse => ({
  session_id: payload.session_id || "ws-session",
  reply: payload.reply || "",
  orchestrator: {},
  data: {},
  trace: [],
  memory: {
    used_messages: 0,
    capacity_messages: 0,
    usage_ratio: 0,
    trim_events: 0,
    saturated: false,
  },
});

const buildProgressResponseFromEvent = (
  payload: WebSocketEventPayload,
): Partial<IADevChatResponse> => ({
  session_id: payload.session_id || "",
  reply: "",
  orchestrator: {},
  data: {},
  trace: [],
  memory: {
    used_messages: 0,
    capacity_messages: 0,
    usage_ratio: 0,
    trim_events: 0,
    saturated: false,
  },
  working_updates: Array.isArray(payload.working_updates)
    ? payload.working_updates
    : payload.status_text
      ? [
          {
            stage: "progress",
            stage_label: "Proceso",
            status: "in_progress",
            summary: payload.status_text,
            display_text: payload.status_text,
            at: new Date().toISOString(),
          },
        ]
      : [],
  reasoning: payload.reasoning || {
    enabled: true,
    status: "running",
    current_next_step: payload.status_text || "",
  },
});

const wait = (ms: number) =>
  new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });

const buildPendingProgressFrames = (): Partial<IADevChatResponse>[] => {
  const now = () => new Date().toISOString();
  return [
    {
      working_updates: [
        {
          stage: "intake",
          stage_label: "Consulta",
          status: "in_progress",
          summary: "Leyendo la consulta y ubicando el contexto.",
          display_text: "Leyendo la consulta y ubicando el contexto.",
          at: now(),
        },
      ],
      reasoning: {
        enabled: true,
        status: "running",
        current_next_step: "clasificar dominio e intencion",
      },
    },
    {
      working_updates: [
        {
          stage: "bootstrap",
          stage_label: "Lectura",
          status: "in_progress",
          summary: "Buscando señales de dominio, entidad y filtros utiles.",
          display_text: "Buscando señales de dominio, entidad y filtros utiles.",
          at: now(),
        },
      ],
      reasoning: {
        enabled: true,
        status: "running",
        current_next_step: "contrastar memoria y rutas posibles",
      },
    },
    {
      working_updates: [
        {
          stage: "planning",
          stage_label: "Ruta",
          status: "in_progress",
          summary: "Comparando la mejor ruta antes de responder.",
          display_text: "Comparando la mejor ruta antes de responder.",
          at: now(),
        },
      ],
      reasoning: {
        enabled: true,
        status: "running",
        current_next_step: "armar la respuesta final con evidencia",
      },
    },
  ];
};

const startPendingProgressPlayback = (
  onProgress?: (response: Partial<IADevChatResponse>) => void,
) => {
  if (!onProgress) return () => {};
  const frames = buildPendingProgressFrames();
  let cancelled = false;
  const timers: number[] = [];
  frames.forEach((frame, index) => {
    const timer = window.setTimeout(() => {
      if (!cancelled) {
        onProgress(frame);
      }
    }, index * 850);
    timers.push(timer);
  });
  return () => {
    cancelled = true;
    timers.forEach((timer) => window.clearTimeout(timer));
  };
};

const playbackResolvedProgress = async (
  response: IADevChatResponse,
  onProgress?: (response: Partial<IADevChatResponse>) => void,
) => {
  if (!onProgress) return;
  const updates = Array.isArray(response.working_updates)
    ? response.working_updates
    : [];
  if (updates.length === 0) {
    if (response.reasoning) {
      onProgress({
        working_updates: [],
        reasoning: response.reasoning,
      });
    }
    return;
  }

  const accumulated: IADevChatResponse["working_updates"] = [];
  for (const update of updates.slice(-4)) {
    accumulated.push(update);
    onProgress({
      working_updates: [...accumulated],
      reasoning: {
        enabled: response.reasoning?.enabled ?? true,
        ...(response.reasoning || {}),
        current_next_step:
          response.reasoning?.current_next_step || update.next_step || "",
      },
    });
    await wait(170);
  }
};

export const useIADevChatTransport = () => {
  const webSocketUrl = useMemo(() => buildDefaultWsUrl(), []);
  const wsRef = useRef<WebSocket | null>(null);
  const isUnmountingRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef(0);
  const pendingRequestsRef = useRef<Map<string, PendingRequest>>(new Map());

  const [connectionState, setConnectionState] = useState<ConnectionState>(
    webSocketUrl ? "connecting" : "disabled",
  );
  const [lastError, setLastError] = useState("");

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = 0;
    }
  }, []);

  const resolvePending = useCallback(
    (requestId: string, response: IADevChatResponse) => {
      const pending = pendingRequestsRef.current.get(requestId);
      if (!pending) return;

      window.clearTimeout(pending.timeoutId);
      pending.resolve(response);
      pendingRequestsRef.current.delete(requestId);
    },
    [],
  );

  const rejectPending = useCallback((requestId: string, error: string) => {
    const pending = pendingRequestsRef.current.get(requestId);
    if (!pending) return;
    window.clearTimeout(pending.timeoutId);
    pending.reject(new Error(error));
    pendingRequestsRef.current.delete(requestId);
  }, []);

  const pickRequestId = useCallback(
    (payload: WebSocketEventPayload): string | null => {
      if (
        payload.request_id &&
        pendingRequestsRef.current.has(payload.request_id)
      ) {
        return payload.request_id;
      }
      const first = pendingRequestsRef.current.keys().next();
      return first.done ? null : first.value;
    },
    [],
  );

  const scheduleReconnect = useCallback(() => {
    if (!webSocketUrl || isUnmountingRef.current) return;
    clearReconnectTimer();
    reconnectAttemptsRef.current += 1;
    const delay = Math.min(
      800 * 2 ** (reconnectAttemptsRef.current - 1),
      MAX_RECONNECT_DELAY_MS,
    );
    setConnectionState("reconnecting");
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = 0;
      if (!isUnmountingRef.current) {
        setConnectionState("connecting");
        wsRef.current = new WebSocket(webSocketUrl);
      }
    }, delay);
  }, [clearReconnectTimer, webSocketUrl]);

  useEffect(() => {
    isUnmountingRef.current = false;
    if (!webSocketUrl) return;

    const ws = new WebSocket(webSocketUrl);
    const pendingRequests = pendingRequestsRef.current;
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0;
      setConnectionState("open");
      setLastError("");
    };

    ws.onmessage = (event) => {
      let payload: WebSocketEventPayload | null = null;
      try {
        payload = JSON.parse(event.data) as WebSocketEventPayload;
      } catch {
        return;
      }

      if (!payload) return;
      const requestId = pickRequestId(payload);
      if (!requestId) return;
      const pending = pendingRequestsRef.current.get(requestId);
      if (!pending) return;

      const eventType = String(payload.type || "").toLowerCase();
      const chunk = payload.chunk || payload.delta || payload.content || "";

      if (eventType === "assistant_start" || eventType === "start") {
        pending.callbacks?.onStart?.();
        return;
      }

      if (
        eventType === "assistant_chunk" ||
        eventType === "chunk" ||
        eventType === "delta"
      ) {
        if (chunk) {
          pending.callbacks?.onChunk?.(chunk);
        }
        return;
      }

      if (
        eventType === "assistant_progress" ||
        eventType === "progress" ||
        eventType === "reasoning_update" ||
        eventType === "working_update"
      ) {
        pending.callbacks?.onProgress?.(
          payload.response ||
            payload.data ||
            buildProgressResponseFromEvent(payload),
        );
        return;
      }

      if (eventType === "assistant_error" || eventType === "error") {
        const errorMessage =
          payload.error || payload.detail || "Error de transporte websocket.";
        rejectPending(requestId, errorMessage);
        setLastError(errorMessage);
        return;
      }

      const responseCandidate = payload.response || payload.data;
      if (responseCandidate && responseCandidate.reply) {
        resolvePending(requestId, responseCandidate);
        return;
      }

      if (payload.reply && payload.session_id) {
        resolvePending(requestId, buildFallbackResponseFromEvent(payload));
      }
    };

    ws.onerror = () => {
      setConnectionState("error");
      setLastError("No se pudo mantener la conexion websocket.");
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (isUnmountingRef.current) {
        setConnectionState("closed");
        return;
      }
      scheduleReconnect();
    };

    return () => {
      isUnmountingRef.current = true;
      clearReconnectTimer();
      ws.close();
      wsRef.current = null;
      pendingRequests.forEach((pending, requestId) => {
        rejectPending(requestId, "La conexion websocket fue cerrada.");
      });
      pendingRequests.clear();
    };
  }, [
    clearReconnectTimer,
    pickRequestId,
    rejectPending,
    resolvePending,
    scheduleReconnect,
    webSocketUrl,
  ]);

  const sendUsingHttpFallback = useCallback(
    async ({
      message,
      sessionId,
      callbacks,
    }: SendMessageParams): Promise<IADevChatResponse> => {
      callbacks?.onStart?.();
      const stopPendingPlayback = startPendingProgressPlayback(
        callbacks?.onProgress,
      );
      const response = await sendIADevMessage({
        message,
        session_id: sessionId || undefined,
      });
      stopPendingPlayback();
      await playbackResolvedProgress(response, callbacks?.onProgress);
      await streamChunks(response.reply, callbacks?.onChunk);
      return response;
    },
    [],
  );

  const sendMessage = useCallback(
    async ({
      message,
      sessionId,
      callbacks,
    }: SendMessageParams): Promise<IADevChatResponse> => {
      const ws = wsRef.current;
      if (!webSocketUrl || !ws || ws.readyState !== WebSocket.OPEN) {
        return sendUsingHttpFallback({ message, sessionId, callbacks });
      }

      const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

      return new Promise<IADevChatResponse>((resolve, reject) => {
        const timeoutId = window.setTimeout(() => {
          rejectPending(
            requestId,
            "Timeout esperando respuesta websocket. Se recomienda reintentar.",
          );
        }, MAX_WS_WAIT_MS);

        pendingRequestsRef.current.set(requestId, {
          id: requestId,
          callbacks,
          resolve,
          reject,
          timeoutId,
        });

        callbacks?.onStart?.();

        ws.send(
          JSON.stringify({
            type: "chat_message",
            request_id: requestId,
            message,
            session_id: sessionId || undefined,
          }),
        );
      });
    },
    [rejectPending, sendUsingHttpFallback, webSocketUrl],
  );

  const transportMode = webSocketUrl ? "websocket" : "http";

  return {
    sendMessage,
    transportMode,
    connectionState,
    lastError,
  };
};
