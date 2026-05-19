"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PageBreadcrumb from "@/components/common/PageBreadCrumb";
import {
  Bot,
  ChevronsLeft,
  ChevronsRight,
  ClipboardList,
  Cpu,
  Database,
  FastForward,
  GitBranch,
  GripHorizontal,
  LayoutPanelLeft,
  Maximize2,
  MessageSquare,
  Minimize2,
  Minus,
  Pause,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Play,
  Plus,
  Rewind,
  RotateCcw,
  SkipBack,
  SkipForward,
} from "lucide-react";
import IADevFlowCanvas from "./flow/IADevFlowCanvas";
import IADevMemoryPanel from "./components/IADevMemoryPanel";
import ScrollToBottomButton from "./chat/components/ScrollToBottomButton";
import { type ChatAttachmentSummary, type ChatMessageModel } from "./chat/types";
import { mergeStreamingResponse } from "./chat/utils/mergeStreamingResponse";
import { normalizeChatPayload } from "./chat/utils/normalizeChatPayload";
import { usePromptHistory } from "./chat/hooks/usePromptHistory";
import { useSmartAutoScroll } from "./chat/hooks/useSmartAutoScroll";
import { useIADevChatTransport } from "./chat/hooks/useIADevChatTransport";
import {
  loadWorkspaceLayout,
  saveWorkspaceLayout,
} from "./persistence/layoutStorage";
import MessageInput from "@/modules/agente-ia/components/MessageInput";
import MessageList from "@/modules/agente-ia/components/MessageList";
import DashboardPanel from "@/modules/agente-ia/components/DashboardPanel";
import TaskStatusBadge from "@/modules/agente-ia/components/TaskStatusBadge";
import {
  buildDashboardSnapshot,
  buildDashboardSnapshotFromMessage,
} from "@/modules/agente-ia/utils/buildDashboardSnapshot";
import {
  createIADevTicket,
  getIADevHealth,
  getIADevTaskStatus,
  resetIADevMemory,
  type IADevAction,
  type IADevChatAttachment,
  type IADevChatResponse,
  type IADevMemoryCandidate,
  type IADevMemoryProposal,
} from "@/services/ia-dev.service";

type ResizeSide = "left" | "right" | null;
type WorkspaceCenterView = "flow" | "dashboard";
type ComposerAttachment = ChatAttachmentSummary & {
  file: File;
  lastModified: number;
};

const LEFT_RAIL_WIDTH = 56;
const LEFT_COLLAPSE_THRESHOLD = 72;
const RIGHT_COLLAPSE_THRESHOLD = 150;
const DEFAULT_LEFT_WIDTH = 300;
const DEFAULT_RIGHT_WIDTH = 420;
const PANEL_STEP = 32;
const TERMINAL_MIN_HEIGHT = 105;
const TERMINAL_DEFAULT_HEIGHT = 220;
const DEFAULT_BACKGROUND_POLL_MS = 1000;
const BACKGROUND_POLL_ERROR_RETRY_MS = 5000;

const DATABASES = [
  {
    name: "cincosas_cincosas",
    tables: [
      "gestionh_ausentismo",
      "dictionary_tables",
      "dictionary_columns",
      "dictionary_relations",
    ],
  },
  {
    name: "cinco_base_de_personal",
    tables: ["cinco_base_de_personal", "supervisores", "cargos", "areas"],
  },
];

const SERVICE_AREAS = [
  { id: "HHGG", domains: ["attendance", "rrhh"] },
  { id: "OPERACIONES", domains: ["operations"] },
  { id: "TRANSPORTE", domains: ["transport"] },
  { id: "VIATICOS", domains: ["viatics"] },
  { id: "NOMINA", domains: ["payroll"] },
  { id: "AUDITORIA", domains: ["audit"] },
];

const AVAILABLE_AGENTS = [
  "analista_agent",
  "rrhh_agent",
  "attendance_agent",
  "transport_agent",
  "operations_agent",
  "viatics_agent",
  "payroll_agent",
  "audit_agent",
];

const ACTIVE_BACKGROUND_STATUSES = new Set([
  "queued",
  "running",
  "resumed",
  "awaiting_approval",
  "paused",
]);

const BASE_ACTIVE_NODE_IDS: string[] = [];

const getAreaFromDomain = (domain?: string | null) => {
  const domainKey = (domain || "").toLowerCase();
  const match = SERVICE_AREAS.find((area) => area.domains.includes(domainKey));
  return match?.id || "HHGG";
};

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const createMessageId = (role: "user" | "assistant") =>
  `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

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
    (message.response?.task?.current_run?.semantic_explanation
      ?.background_status as Record<string, unknown> | undefined);
  const candidates = [polling?.next_poll_after_ms, polling?.poll_interval_ms];
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

type ProcessRun = {
  id: string;
  createdAt: number;
  query: string;
  reply: string;
  agent: string;
  domain: string;
  usedTools: string[];
  channels: string[];
  trace: IADevChatResponse["trace"];
  activeNodes: string[];
};

const ResizeHandle = ({ onMouseDown }: { onMouseDown: () => void }) => (
  <button
    aria-label="Resize panel"
    onMouseDown={onMouseDown}
    className="group relative w-2 shrink-0 cursor-col-resize bg-gray-50 transition hover:bg-gray-100 dark:bg-gray-900 dark:hover:bg-gray-800"
  >
    <span className="group-hover:bg-brand-500 absolute top-1/2 left-1/2 h-14 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gray-300 dark:bg-gray-700 dark:group-hover:bg-brand-400" />
  </button>
);

const IADevWorkspace = () => {
  const workspaceRef = useRef<HTMLDivElement>(null);
  const centerSectionRef = useRef<HTMLElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const undoStackRef = useRef<string[]>([]);
  const redoStackRef = useRef<string[]>([]);
  const backgroundPollersRef = useRef<Map<string, { cancel: () => void }>>(
    new Map(),
  );

  const initialWorkspaceLayout = useMemo(() => loadWorkspaceLayout(), []);
  const [leftOpen, setLeftOpen] = useState(
    initialWorkspaceLayout?.leftOpen ?? true,
  );
  const [rightOpen, setRightOpen] = useState(
    initialWorkspaceLayout?.rightOpen ?? true,
  );
  const [leftWidth, setLeftWidth] = useState(
    initialWorkspaceLayout?.leftWidth ?? DEFAULT_LEFT_WIDTH,
  );
  const [rightWidth, setRightWidth] = useState(
    initialWorkspaceLayout?.rightWidth ?? DEFAULT_RIGHT_WIDTH,
  );
  const [resizeSide, setResizeSide] = useState<ResizeSide>(null);
  const [centerView, setCenterView] = useState<WorkspaceCenterView>("flow");
  const { pushPrompt, navigate, resetNavigation } = usePromptHistory();
  const {
    sendMessage,
    transportMode,
    connectionState,
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
  const [composerAttachments, setComposerAttachments] = useState<
    ComposerAttachment[]
  >([]);
  const [messages, setMessages] = useState<ChatMessageModel[]>([
    {
      id: createMessageId("assistant"),
      role: "assistant",
      content:
        "IA DEV listo. Describe una consulta y te muestro agente, tools y trazabilidad.",
      createdAt: Date.now(),
      status: "final",
    },
  ]);
  const [messageWindowSize, setMessageWindowSize] = useState(80);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [chatStatus, setChatStatus] = useState("");
  const [latestMemoryCandidates, setLatestMemoryCandidates] = useState<
    IADevMemoryCandidate[]
  >([]);
  const [latestPendingProposals, setLatestPendingProposals] = useState<
    IADevMemoryProposal[]
  >([]);
  const [latestMemoryActions, setLatestMemoryActions] = useState<IADevAction[]>(
    [],
  );
  const [activeAgent, setActiveAgent] = useState<string>("analista_agent");
  const [activeArea, setActiveArea] = useState<string>("HHGG");
  const [activeNodeIds, setActiveNodeIds] =
    useState<string[]>(BASE_ACTIVE_NODE_IDS);
  const [aiDictionaryStatus, setAiDictionaryStatus] = useState<{
    ok: boolean;
    table?: string | null;
    rows?: number;
    error?: string;
  } | null>(null);
  const [runHistory, setRunHistory] = useState<ProcessRun[]>([]);
  const [selectedRunIndex, setSelectedRunIndex] = useState(-1);
  const [selectedStepIndex, setSelectedStepIndex] = useState(0);
  const [isPlaybackRunning, setIsPlaybackRunning] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<0.5 | 1 | 2>(1);
  const [terminalHeight, setTerminalHeight] = useState(TERMINAL_DEFAULT_HEIGHT);
  const [terminalDetached, setTerminalDetached] = useState(false);
  const [resizingTerminal, setResizingTerminal] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(
    null,
  );
  const [composerResetSignal, setComposerResetSignal] = useState(0);
  const [selectedDashboardMessageId, setSelectedDashboardMessageId] = useState<
    string | null
  >(null);

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

  const clearComposerAttachments = () => {
    setComposerAttachments([]);
  };

  const addComposerFiles = (files: File[]) => {
    setComposerAttachments((prev) => {
      const next = [...prev];
      files.forEach((file) => {
        const existing = next.find(
          (attachment) =>
            attachment.name === file.name &&
            attachment.size === file.size &&
            attachment.lastModified === file.lastModified,
        );
        if (existing) return;
        next.push({
          id: createAttachmentId(file),
          name: file.name,
          mimeType: file.type || "application/octet-stream",
          size: file.size,
          kind: inferAttachmentKind(file),
          file,
          lastModified: file.lastModified,
        });
      });
      return next;
    });
  };

  const removeComposerAttachment = (attachmentId: string) => {
    setComposerAttachments((prev) =>
      prev.filter((attachment) => attachment.id !== attachmentId),
    );
  };

  const visibleMessages = useMemo(
    () => messages.slice(-messageWindowSize),
    [messageWindowSize, messages],
  );
  const hasCollapsedMessages = messages.length > messageWindowSize;
  const transportLabel = useMemo(() => {
    if (transportMode === "websocket") {
      return `WS ${connectionState}`;
    }
    return "HTTP";
  }, [connectionState, transportMode]);

  const selectedRun =
    selectedRunIndex >= 0 ? runHistory[selectedRunIndex] : null;
  const selectedTrace = selectedRun?.trace ?? [];
  const maxStepIndex = Math.max(0, selectedTrace.length - 1);
  const currentStep = selectedTrace[selectedStepIndex] ?? null;

  const dashboardEntries = useMemo(() => {
    const assistantMessages = messages.filter(
      (message) =>
        message.role === "assistant" &&
        message.content.trim() &&
        message.response != null,
    );

    return assistantMessages.map((message, index) => {
      const snapshot = buildDashboardSnapshotFromMessage(message);
      const label = `Respuesta ${index + 1}`;
      const shortLabel = snapshot.hasStructuredContent
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
  const resolvedSelectedDashboardMessageId = useMemo(() => {
    if (
      selectedDashboardMessageId &&
      dashboardEntries.some(
        (entry) => entry.messageId === selectedDashboardMessageId,
      )
    ) {
      return selectedDashboardMessageId;
    }
    return latestDashboardEntry?.messageId ?? null;
  }, [dashboardEntries, latestDashboardEntry?.messageId, selectedDashboardMessageId]);

  const dashboardSnapshot = useMemo(
    () => buildDashboardSnapshot(messages, resolvedSelectedDashboardMessageId),
    [messages, resolvedSelectedDashboardMessageId],
  );
  const liveDashboardSnapshot = latestDashboardEntry?.snapshot ?? null;
  const selectedDashboardIndex = dashboardEntries.findIndex(
    (entry) => entry.messageId === resolvedSelectedDashboardMessageId,
  );
  const selectedDashboardLabel =
    dashboardEntries.find(
      (entry) => entry.messageId === resolvedSelectedDashboardMessageId,
    )?.label || "Consulta actual";
  const semanticHint =
    dashboardSnapshot.semanticExplanation?.understood_as?.trim() || "";
  const clarificationQuestion = dashboardSnapshot.clarificationQuestion || "";

  const effectiveChatStatus = useMemo(() => {
    if (transportError) {
      return "No fue posible conectar con el servicio en este momento.";
    }
    if (streamingMessageId) {
      return dashboardSnapshot.taskPreparationLabel;
    }
    if (chatStatus.trim()) {
      return chatStatus;
    }
    return "Listo para consultas analiticas.";
  }, [
    chatStatus,
    dashboardSnapshot.taskPreparationLabel,
    streamingMessageId,
    transportError,
  ]);

  const resolveStepActiveNodes = (
    run: ProcessRun | null,
    stepIndex: number,
  ) => {
    if (!run) return BASE_ACTIVE_NODE_IDS;
    const step = run.trace[stepIndex];
    if (step?.active_nodes && step.active_nodes.length > 0) {
      return step.active_nodes;
    }
    if (run.activeNodes.length > 0) {
      return run.activeNodes;
    }
    return BASE_ACTIVE_NODE_IDS;
  };

  const stringifyDetail = (detail: unknown) => {
    if (detail == null) return "";
    if (typeof detail === "string") return detail;
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  };

  const appendAssistantMessage = (
    content: string,
    overrides?: Partial<ChatMessageModel>,
  ) => {
    setMessages((prev) => [
      ...prev,
      {
        id: createMessageId("assistant"),
        role: "assistant",
        content,
        createdAt: Date.now(),
        status: "final",
        ...overrides,
      },
    ]);
    notifyContentChanged("new-message", { behavior: "smooth" });
  };

  const getWorkspaceWidth = () =>
    workspaceRef.current?.getBoundingClientRect().width ?? 0;

  const getMaxLeftWidth = () => {
    const reserved = LEFT_RAIL_WIDTH + (rightOpen ? rightWidth : 0);
    return Math.max(0, getWorkspaceWidth() - reserved);
  };

  const getMaxRightWidth = () => {
    const reserved = LEFT_RAIL_WIDTH + (leftOpen ? leftWidth : 0);
    return Math.max(0, getWorkspaceWidth() - reserved);
  };

  const openLeftPanel = () => {
    setLeftOpen(true);
    setLeftWidth((prev) => {
      const next = prev > LEFT_COLLAPSE_THRESHOLD ? prev : DEFAULT_LEFT_WIDTH;
      return clamp(next, 0, getMaxLeftWidth());
    });
  };

  const openRightPanel = () => {
    setRightOpen(true);
    setRightWidth((prev) => {
      const next =
        prev >= RIGHT_COLLAPSE_THRESHOLD ? prev : DEFAULT_RIGHT_WIDTH;
      return clamp(next, 0, getMaxRightWidth());
    });
  };

  const reduceLeftPanel = () => {
    setLeftWidth((prev) => {
      const next = Math.max(0, prev - PANEL_STEP);
      if (next < LEFT_COLLAPSE_THRESHOLD) {
        setLeftOpen(false);
        return 0;
      }
      return next;
    });
  };

  const expandLeftPanel = () => {
    setLeftOpen(true);
    setLeftWidth((prev) => {
      const base = prev > LEFT_COLLAPSE_THRESHOLD ? prev : DEFAULT_LEFT_WIDTH;
      return clamp(base + PANEL_STEP, 0, getMaxLeftWidth());
    });
  };

  const reduceRightPanel = () => {
    setRightWidth((prev) => {
      const next = Math.max(0, prev - PANEL_STEP);
      if (next < RIGHT_COLLAPSE_THRESHOLD) {
        setRightOpen(false);
        return 0;
      }
      return next;
    });
  };

  const expandRightPanel = () => {
    setRightOpen(true);
    setRightWidth((prev) => {
      const base =
        prev >= RIGHT_COLLAPSE_THRESHOLD ? prev : DEFAULT_RIGHT_WIDTH;
      return clamp(base + PANEL_STEP, 0, getMaxRightWidth());
    });
  };

  const registerRunFromResponse = useCallback(
    (
      runId: string,
      query: string,
      result: IADevChatResponse,
      createdAt?: number,
    ) => {
      const channels = Array.from(
        new Set([
          `agent:${result.orchestrator.selected_agent || "analista_agent"}`,
          `domain:${result.orchestrator.domain || "general"}`,
          ...(result.orchestrator.used_tools ?? []).map(
            (tool) => `tool:${tool}`,
          ),
          ...(result.trace ?? []).map((step) => `phase:${step.phase}`),
        ]),
      );

      const processRun: ProcessRun = {
        id: runId,
        createdAt: createdAt ?? Date.now(),
        query,
        reply: result.reply,
        agent: result.orchestrator.selected_agent || "analista_agent",
        domain: result.orchestrator.domain || "general",
        usedTools: result.orchestrator.used_tools ?? [],
        channels,
        trace: result.trace ?? [],
        activeNodes: result.active_nodes ?? [],
      };

      setRunHistory((prev) => {
        const nextBase = prev.filter((item) => item.id !== runId);
        const next = [...nextBase, processRun].slice(-30);
        const nextIndex = next.findIndex((item) => item.id === runId);
        setSelectedRunIndex(nextIndex);
        return next;
      });
      setSelectedStepIndex(0);
      setIsPlaybackRunning(false);
      setActiveNodeIds(result.active_nodes ?? BASE_ACTIVE_NODE_IDS);
      setActiveAgent(result.orchestrator.selected_agent || "analista_agent");
      setActiveArea(getAreaFromDomain(result.orchestrator.domain || "general"));
    },
    [],
  );

  const selectDashboardMessage = (messageId: string) => {
    setSelectedDashboardMessageId(messageId);
    setCenterView("dashboard");
  };

  const copyTextToClipboard = async (text: string, successStatus: string) => {
    const normalized = text.trim();
    if (!normalized || typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }

    try {
      await navigator.clipboard.writeText(normalized);
      setChatStatus(successStatus);
    } catch {
      setChatStatus("No fue posible copiar el contenido.");
    }
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

  const prepareRelatedQuery = () => {
    const base = dashboardSnapshot.executiveSummary || dashboardSnapshot.summary;
    setChatInputTracked(`Quiero profundizar sobre esto: ${base}`);
  };

  useEffect(() => {
    if (!resizeSide) return;

    const onMouseMove = (event: MouseEvent) => {
      const container = workspaceRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();

      if (resizeSide === "left" && leftOpen) {
        const maxAllowed = Math.max(
          0,
          rect.width - LEFT_RAIL_WIDTH - (rightOpen ? rightWidth : 0),
        );
        const next = clamp(
          event.clientX - rect.left - LEFT_RAIL_WIDTH,
          0,
          maxAllowed,
        );
        if (next < LEFT_COLLAPSE_THRESHOLD) {
          setLeftOpen(false);
          setLeftWidth(0);
          return;
        }
        setLeftWidth(next);
      }

      if (resizeSide === "right" && rightOpen) {
        const maxAllowed = Math.max(
          0,
          rect.width - LEFT_RAIL_WIDTH - (leftOpen ? leftWidth : 0),
        );
        const next = clamp(rect.right - event.clientX, 0, maxAllowed);
        if (next < RIGHT_COLLAPSE_THRESHOLD) {
          setRightOpen(false);
          setRightWidth(0);
          return;
        }
        setRightWidth(next);
      }
    };

    const onMouseUp = () => {
      setResizeSide(null);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [leftOpen, leftWidth, resizeSide, rightOpen, rightWidth]);

  useEffect(() => {
    const syncPanelWidths = () => {
      const workspaceWidth =
        workspaceRef.current?.getBoundingClientRect().width ?? 0;

      if (leftOpen) {
        const maxLeft = Math.max(
          0,
          workspaceWidth - LEFT_RAIL_WIDTH - (rightOpen ? rightWidth : 0),
        );
        if (maxLeft < LEFT_COLLAPSE_THRESHOLD) {
          setLeftOpen(false);
          setLeftWidth(0);
        } else {
          setLeftWidth((prev) => clamp(prev, 0, maxLeft));
        }
      }

      if (rightOpen) {
        const maxRight = Math.max(
          0,
          workspaceWidth - LEFT_RAIL_WIDTH - (leftOpen ? leftWidth : 0),
        );
        if (maxRight < RIGHT_COLLAPSE_THRESHOLD) {
          setRightOpen(false);
          setRightWidth(0);
        } else {
          setRightWidth((prev) => clamp(prev, 0, maxRight));
        }
      }
    };

    syncPanelWidths();
    window.addEventListener("resize", syncPanelWidths);
    return () => window.removeEventListener("resize", syncPanelWidths);
  }, [leftOpen, rightOpen, leftWidth, rightWidth]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      saveWorkspaceLayout({
        leftOpen,
        rightOpen,
        leftWidth,
        rightWidth,
      });
    }, 180);

    return () => window.clearTimeout(timer);
  }, [leftOpen, rightOpen, leftWidth, rightWidth]);

  useEffect(() => {
    let active = true;

    const loadHealth = async () => {
      try {
        const health = await getIADevHealth();
        if (!active) return;
        setAiDictionaryStatus(health.data_sources.ai_dictionary);
      } catch {
        if (!active) return;
        setAiDictionaryStatus({
          ok: false,
          error: "No se pudo consultar ia-dev/health",
        });
      }
    };

    void loadHealth();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (transportError) {
      setChatStatus(`Transporte: ${transportError}`);
    }
  }, [transportError]);

  useEffect(() => {
    if (!isPlaybackRunning) return;
    if (selectedTrace.length === 0) return;
    if (selectedStepIndex >= selectedTrace.length - 1) {
      setIsPlaybackRunning(false);
      return;
    }

    const intervalMs =
      playbackSpeed === 0.5 ? 1800 : playbackSpeed === 2 ? 500 : 1000;
    const timer = window.setTimeout(() => {
      setSelectedStepIndex((prev) =>
        Math.min(prev + 1, selectedTrace.length - 1),
      );
    }, intervalMs);

    return () => window.clearTimeout(timer);
  }, [
    isPlaybackRunning,
    playbackSpeed,
    selectedStepIndex,
    selectedTrace.length,
  ]);

  useEffect(() => {
    if (!selectedRun) {
      setActiveNodeIds(BASE_ACTIVE_NODE_IDS);
      setActiveAgent("analista_agent");
      setActiveArea("HHGG");
      return;
    }

    setActiveNodeIds(resolveStepActiveNodes(selectedRun, selectedStepIndex));
    setActiveAgent(selectedRun.agent || "analista_agent");
    setActiveArea(getAreaFromDomain(selectedRun.domain));
  }, [selectedRun, selectedStepIndex]);

  useEffect(() => {
    if (rightOpen) {
      window.setTimeout(() => {
        scrollToBottom("auto");
      }, 40);
    }
  }, [rightOpen, scrollToBottom]);

  useEffect(() => {
    if (!resizingTerminal || terminalDetached) return;

    const onMouseMove = (event: MouseEvent) => {
      const container = centerSectionRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const maxHeight = Math.max(
        TERMINAL_MIN_HEIGHT,
        Math.floor(rect.height * 0.75),
      );
      const nextHeight = clamp(
        rect.bottom - event.clientY - 16,
        TERMINAL_MIN_HEIGHT,
        maxHeight,
      );
      setTerminalHeight(nextHeight);
    };

    const onMouseUp = () => {
      setResizingTerminal(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [resizingTerminal, terminalDetached]);

  useEffect(() => {
    const pollableMessages = messages.filter(isPollableBackgroundMessage);
    const activeRunIds = new Set(pollableMessages.map(extractBackgroundRunId));

    backgroundPollersRef.current.forEach((poller, backgroundRunId) => {
      if (activeRunIds.has(backgroundRunId)) return;
      poller.cancel();
      backgroundPollersRef.current.delete(backgroundRunId);
    });

    pollableMessages.forEach((message) => {
      const backgroundRunId = extractBackgroundRunId(message);
      if (!backgroundRunId || backgroundPollersRef.current.has(backgroundRunId)) {
        return;
      }

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
            { background_run_id: backgroundRunId },
            { signal: controller.signal },
          );
          if (cancelled) return;

          consecutiveErrors = 0;
          const normalizedPayload = normalizeChatPayload(result);
          const assistantReply = result.reply || result.task?.current_run?.reply || "";
          const nextStatus = String(
            result.task?.current_run?.background?.run_status ||
              result.task?.current_run?.status ||
              "",
          )
            .trim()
            .toLowerCase();

          setMessages((prev) =>
            prev.map((item) =>
              item.id === message.id
                ? {
                    ...item,
                    content: assistantReply || item.content,
                    status: ACTIVE_BACKGROUND_STATUSES.has(nextStatus)
                      ? ("streaming" as const)
                      : ("final" as const),
                    response: result,
                    normalized: normalizedPayload,
                    actions: result.actions ?? item.actions ?? [],
                    memoryCandidates:
                      result.memory_candidates ?? item.memoryCandidates ?? [],
                    pendingProposals:
                      result.pending_proposals ?? item.pendingProposals ?? [],
                  }
                : item,
            ),
          );

          setSessionId(result.session_id);
          setLatestMemoryCandidates(result.memory_candidates ?? []);
          setLatestPendingProposals(result.pending_proposals ?? []);
          setLatestMemoryActions(result.actions ?? []);
          registerRunFromResponse(message.id, "Seguimiento background", result, message.createdAt);

          if (result.data_sources?.ai_dictionary) {
            setAiDictionaryStatus(result.data_sources.ai_dictionary);
          }

          if (ACTIVE_BACKGROUND_STATUSES.has(nextStatus)) {
            scheduleNext(extractBackgroundPollIntervalMs(message));
          } else {
            backgroundPollersRef.current.delete(backgroundRunId);
            notifyContentChanged("stream-end", { behavior: "smooth" });
          }
        } catch (error) {
          if (cancelled || (error instanceof DOMException && error.name === "AbortError")) {
            return;
          }
          consecutiveErrors += 1;
          scheduleNext(BACKGROUND_POLL_ERROR_RETRY_MS * Math.min(consecutiveErrors, 3));
        } finally {
          inFlight = false;
        }
      };

      backgroundPollersRef.current.set(backgroundRunId, { cancel });
      scheduleNext(extractBackgroundPollIntervalMs(message));
    });

    const pollers = backgroundPollersRef.current;
    return () => {
      if (messages.length > 0) return;
      pollers.forEach((poller) => poller.cancel());
      pollers.clear();
    };
  }, [messages, notifyContentChanged, registerRunFromResponse]);

  useEffect(() => {
    const pollers = backgroundPollersRef.current;
    return () => {
      pollers.forEach((poller) => poller.cancel());
      pollers.clear();
    };
  }, []);

  const submitChat = async (overridePrompt?: string) => {
    const value = (overridePrompt ?? chatInput).trim();
    if (!value || isSubmitting) return;

    const userMessageId = createMessageId("user");
    const assistantMessageId = createMessageId("assistant");
    const attachmentsForSubmission = composerAttachments.map((attachment) => ({
      ...attachment,
    }));
    const userMessageAttachments = attachmentsForSubmission.map((attachment) =>
      toAttachmentSummary(attachment),
    );

    let transportAttachments: IADevChatAttachment[] = [];
    if (attachmentsForSubmission.length > 0) {
      try {
        transportAttachments = await buildTransportAttachments(
          attachmentsForSubmission,
        );
      } catch {
        setChatStatus("No fue posible preparar los adjuntos para enviarlos.");
        return;
      }
    }

    setMessages((prev) => [
      ...prev,
      {
        id: userMessageId,
        role: "user",
        content: value,
        createdAt: Date.now(),
        status: "final",
        attachments: userMessageAttachments,
      },
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        createdAt: Date.now(),
        status: "streaming",
      },
    ]);
    setChatInput("");
    clearComposerAttachments();
    setComposerResetSignal((prev) => prev + 1);
    resetChatInputHistory();
    pushPrompt(value);
    resetNavigation();
    setStreamingMessageId(assistantMessageId);
    setIsPlaybackRunning(false);
    setSelectedStepIndex(0);
    setSelectedRunIndex(-1);
    setActiveNodeIds(BASE_ACTIVE_NODE_IDS);
    setActiveAgent("analista_agent");
    setActiveArea("HHGG");
    notifyContentChanged("user-submit", { behavior: "smooth", force: true });

    try {
      setIsSubmitting(true);
      const result = await sendMessage({
        message: value,
        sessionId: sessionId ?? undefined,
        attachments: transportAttachments,
        callbacks: {
          onStart: () => {
            notifyContentChanged("stream-start", { behavior: "smooth" });
          },
          onProgress: (progress) => {
            setMessages((prev) =>
              prev.map((message) =>
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
            );
            notifyContentChanged("stream-chunk", { behavior: "auto" });
          },
          onChunk: (chunk) => {
            if (!chunk) return;
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantMessageId
                  ? {
                      ...message,
                      content: `${message.content}${chunk}`,
                      status: "streaming",
                    }
                  : message,
              ),
            );
            notifyContentChanged("stream-chunk", { behavior: "auto" });
          },
        },
      });

      setSessionId(result.session_id);
      const normalizedPayload = normalizeChatPayload(result);
      const nextStatus = String(
        result.task?.current_run?.background?.run_status ||
          result.task?.current_run?.status ||
          "",
      )
        .trim()
        .toLowerCase();

      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: result.reply || message.content,
                status: ACTIVE_BACKGROUND_STATUSES.has(nextStatus)
                  ? ("streaming" as const)
                  : ("final" as const),
                response: result,
                normalized: normalizedPayload,
                actions: result.actions ?? [],
                memoryCandidates: result.memory_candidates ?? [],
                pendingProposals: result.pending_proposals ?? [],
              }
            : message,
        ),
      );
      setLatestMemoryCandidates(result.memory_candidates ?? []);
      setLatestPendingProposals(result.pending_proposals ?? []);
      setLatestMemoryActions(result.actions ?? []);
      registerRunFromResponse(assistantMessageId, value, result);

      setChatStatus(
        `Sesion ${result.session_id.slice(0, 8)} activa | ${transportLabel}`,
      );
      if (result.data_sources?.ai_dictionary) {
        setAiDictionaryStatus(result.data_sources.ai_dictionary);
      }
      setSelectedDashboardMessageId(assistantMessageId);
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
            : "No fue posible procesar la consulta con IA DEV.";

      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                status: "error",
                content: `Error de integracion IA DEV: ${detail}`,
                error: detail,
              }
            : message,
        ),
      );
      setChatStatus("Error de conexion con IA DEV");
    } finally {
      setStreamingMessageId(null);
      setIsSubmitting(false);
    }
  };

  const clearSessionMemory = async () => {
    if (!sessionId || isSubmitting) return;
    try {
      setIsSubmitting(true);
      setChatInput("");
      clearComposerAttachments();
      setComposerResetSignal((prev) => prev + 1);
      resetChatInputHistory();
      await resetIADevMemory(sessionId);
      setLatestMemoryCandidates([]);
      setLatestPendingProposals([]);
      setLatestMemoryActions([]);
      appendAssistantMessage(
        "Memoria de la sesion reiniciada. Continuamos con contexto limpio.",
      );
      setChatStatus(`Sesion ${sessionId.slice(0, 8)} reiniciada`);
    } catch {
      appendAssistantMessage("No fue posible reiniciar memoria en este momento.", {
        status: "error",
      });
      setChatStatus("No se pudo reiniciar la memoria");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleActionClick = async (action: IADevAction) => {
    if (isSubmitting) return;
    if (action.type === "memory_review") {
      setChatStatus(
        "Panel de memoria abierto para revisar propuestas y auditoria.",
      );
      return;
    }
    if (action.type === "render_chart") {
      setCenterView("dashboard");
      setChatStatus("La visualizacion operativa ya se muestra en el dashboard.");
      return;
    }
    if (action.type !== "create_ticket") {
      const query = getSuggestionQuery(action);
      if (!query) return;
      await submitChat(query);
      return;
    }

    const title = action.payload?.title?.trim() || "Solicitud desde IA DEV";
    const description =
      action.payload?.description?.trim() ||
      "Solicitud generada desde interaccion IA DEV.";
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
      setChatStatus(`Ticket ${created.ticket.ticket_id} creado`);
    } catch {
      appendAssistantMessage("No fue posible crear el ticket en este momento.", {
        status: "error",
      });
      setChatStatus("Error al crear ticket");
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderTerminalPanel = (detached: boolean) => (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-gray-700/40 bg-slate-950 text-slate-200">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2 text-xs">
        <div className="min-w-0">
          <p className="truncate font-semibold text-slate-100">
            Consola Orquestador
          </p>
          {selectedRun ? (
            <p className="truncate text-[11px] text-slate-400">
              ultimo proceso: {selectedRun.query}
            </p>
          ) : (
            <p className="text-[11px] text-slate-500">
              aun no hay procesos registrados
            </p>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={openPreviousRun}
            className="rounded p-1 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
            disabled={selectedRunIndex <= 0}
            title="Proceso anterior"
          >
            <ChevronsLeft size={14} />
          </button>
          <button
            type="button"
            onClick={openNextRun}
            className="rounded p-1 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
            disabled={
              selectedRunIndex < 0 || selectedRunIndex >= runHistory.length - 1
            }
            title="Proceso siguiente"
          >
            <ChevronsRight size={14} />
          </button>
          <button
            type="button"
            onClick={() => setTerminalDetached((prev) => !prev)}
            className="rounded p-1 text-slate-300 hover:bg-slate-800"
            title={detached ? "Acoplar terminal" : "Desacoplar terminal"}
          >
            {detached ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      <div className="border-b border-slate-800 px-3 py-2">
        <div className="mb-2 flex flex-wrap gap-1">
          {selectedRun?.channels.slice(0, 12).map((channel) => (
            <span
              key={channel}
              className="rounded-full border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300"
            >
              {channel}
            </span>
          ))}
        </div>
        <input
          type="range"
          min={0}
          max={maxStepIndex}
          value={selectedStepIndex}
          disabled={!selectedRun || selectedTrace.length === 0}
          onChange={(event) => {
            setIsPlaybackRunning(false);
            setSelectedStepIndex(Number(event.target.value));
          }}
          className="accent-brand-500 h-1.5 w-full cursor-pointer"
        />
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-3 py-2 font-mono text-[11px] leading-5">
        {selectedRun && selectedTrace.length > 0 ? (
          <div className="space-y-1">
            {selectedTrace
              .slice(0, selectedStepIndex + 1)
              .map((step, stepIndex) => (
                <div
                  key={`${step.phase}-${stepIndex}`}
                  className="text-slate-300"
                >
                  <span className="text-slate-500">[{step.at}]</span>{" "}
                  <span className="text-cyan-300">{step.phase}</span>{" "}
                  <span
                    className={
                      step.status === "ok"
                        ? "text-emerald-300"
                        : step.status === "warning"
                          ? "text-amber-300"
                          : "text-rose-300"
                    }
                  >
                    ({step.status})
                  </span>{" "}
                  <span className="text-slate-200">
                    {stringifyDetail(step.detail)}
                  </span>
                </div>
              ))}
          </div>
        ) : (
          <p className="text-slate-500">
            Esperando ejecucion del orquestador...
          </p>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-slate-800 px-3 py-2 text-xs">
        <div className="text-slate-400">
          paso {selectedTrace.length === 0 ? 0 : selectedStepIndex + 1}/
          {selectedTrace.length}
          {currentStep && (
            <span className="ml-2 text-slate-300">
              fase actual: {currentStep.phase}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={goToFirstStep}
            className="rounded p-1 text-slate-200 hover:bg-slate-800 disabled:opacity-40"
            disabled={selectedTrace.length === 0 || selectedStepIndex <= 0}
            title="Primer paso"
          >
            <SkipBack size={14} />
          </button>
          <button
            type="button"
            onClick={moveStepBackward}
            className="rounded p-1 text-slate-200 hover:bg-slate-800 disabled:opacity-40"
            disabled={selectedTrace.length === 0 || selectedStepIndex <= 0}
            title="Paso anterior"
          >
            <Rewind size={14} />
          </button>
          <button
            type="button"
            onClick={() => setIsPlaybackRunning((prev) => !prev)}
            className="rounded p-1 text-slate-200 hover:bg-slate-800 disabled:opacity-40"
            disabled={selectedTrace.length === 0}
            title={isPlaybackRunning ? "Pause" : "Play"}
          >
            {isPlaybackRunning ? <Pause size={14} /> : <Play size={14} />}
          </button>
          <button
            type="button"
            onClick={moveStepForward}
            className="rounded p-1 text-slate-200 hover:bg-slate-800 disabled:opacity-40"
            disabled={
              selectedTrace.length === 0 || selectedStepIndex >= maxStepIndex
            }
            title="Paso siguiente"
          >
            <FastForward size={14} />
          </button>
          <button
            type="button"
            onClick={goToLastStep}
            className="rounded p-1 text-slate-200 hover:bg-slate-800 disabled:opacity-40"
            disabled={
              selectedTrace.length === 0 || selectedStepIndex >= maxStepIndex
            }
            title="Ultimo paso"
          >
            <SkipForward size={14} />
          </button>
          <button
            type="button"
            onClick={() => setPlaybackSpeed(0.5)}
            className={`rounded px-2 py-1 ${
              playbackSpeed === 0.5
                ? "bg-brand-500/25 text-brand-200"
                : "text-slate-300 hover:bg-slate-800"
            }`}
            title="Slow"
          >
            slow
          </button>
          <button
            type="button"
            onClick={() => setPlaybackSpeed(1)}
            className={`rounded px-2 py-1 ${
              playbackSpeed === 1
                ? "bg-brand-500/25 text-brand-200"
                : "text-slate-300 hover:bg-slate-800"
            }`}
            title="Normal"
          >
            1x
          </button>
          <button
            type="button"
            onClick={() => setPlaybackSpeed(2)}
            className={`rounded px-2 py-1 ${
              playbackSpeed === 2
                ? "bg-brand-500/25 text-brand-200"
                : "text-slate-300 hover:bg-slate-800"
            }`}
            title="Fast"
          >
            fast
          </button>
        </div>
      </div>
    </div>
  );

  const moveStepBackward = () => {
    setIsPlaybackRunning(false);
    setSelectedStepIndex((prev) => Math.max(0, prev - 1));
  };

  const moveStepForward = () => {
    setIsPlaybackRunning(false);
    setSelectedStepIndex((prev) => Math.min(maxStepIndex, prev + 1));
  };

  const goToFirstStep = () => {
    setIsPlaybackRunning(false);
    setSelectedStepIndex(0);
  };

  const goToLastStep = () => {
    setIsPlaybackRunning(false);
    setSelectedStepIndex(maxStepIndex);
  };

  const openPreviousRun = () => {
    if (runHistory.length === 0) return;
    setIsPlaybackRunning(false);
    setSelectedRunIndex((prev) => Math.max(0, prev - 1));
    setSelectedStepIndex(0);
  };

  const openNextRun = () => {
    if (runHistory.length === 0) return;
    setIsPlaybackRunning(false);
    setSelectedRunIndex((prev) => Math.min(runHistory.length - 1, prev + 1));
    setSelectedStepIndex(0);
  };

  return (
    <div className="w-full min-w-0 overflow-hidden">
      <PageBreadcrumb pageTitle={["Programacion", "IA DEV"]} />

      <div className="h-[calc(100vh-190px)] min-h-[650px] w-full min-w-0">
        <div
          ref={workspaceRef}
          className="flex h-full min-w-0 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/3"
        >
          <aside className="flex w-14 shrink-0 flex-col items-center gap-2 border-r border-gray-200 bg-gray-50 py-3 dark:border-gray-800 dark:bg-gray-900">
            <button
              title="Bases de datos"
              onClick={() => {
                if (leftOpen) {
                  setLeftOpen(false);
                  return;
                }
                openLeftPanel();
              }}
              className={`inline-flex h-10 w-10 items-center justify-center rounded-lg transition ${
                leftOpen
                  ? "bg-brand-500 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-100 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
              }`}
            >
              <Database size={18} />
            </button>
          </aside>

          {leftOpen && (
            <section
              className="flex shrink-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
              style={{ width: leftWidth }}
            >
              <div className="flex items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-800">
                <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-gray-800 dark:text-white/90">
                  <Database size={16} />
                  <span className="truncate">Bases y tablas</span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={reduceLeftPanel}
                    className="rounded-md p-1 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                    title="Reducir"
                  >
                    <Minus size={14} />
                  </button>
                  <button
                    onClick={expandLeftPanel}
                    className="rounded-md p-1 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                    title="Ampliar"
                  >
                    <Plus size={14} />
                  </button>
                  <button
                    onClick={() => setLeftOpen(false)}
                    className="rounded-md p-1 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                    title="Contraer"
                  >
                    <PanelLeftClose size={16} />
                  </button>
                </div>
              </div>

              <div className="flex-1 space-y-4 overflow-auto p-3">
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-800/70">
                  <p className="mb-2 text-sm font-semibold text-gray-800 dark:text-white/90">
                    ai_dictionary
                  </p>
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
                        aiDictionaryStatus?.ok
                          ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                          : "border-red-300 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-900/30 dark:text-red-300"
                      }`}
                    >
                      {aiDictionaryStatus?.ok ? "Conectado" : "Sin conexion"}
                    </span>
                    {typeof aiDictionaryStatus?.rows === "number" && (
                      <span className="text-xs text-gray-500 dark:text-gray-300">
                        filas: {aiDictionaryStatus.rows}
                      </span>
                    )}
                  </div>
                  {aiDictionaryStatus?.table && (
                    <p
                      className="mt-2 truncate text-xs text-gray-500 dark:text-gray-300"
                      title={aiDictionaryStatus.table}
                    >
                      {aiDictionaryStatus.table}
                    </p>
                  )}
                  {aiDictionaryStatus?.error && (
                    <p className="mt-2 text-xs text-red-600 dark:text-red-300">
                      {aiDictionaryStatus.error}
                    </p>
                  )}
                </div>

                {DATABASES.map((db) => (
                  <div
                    key={db.name}
                    className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-800/70"
                  >
                    <p
                      className="mb-2 truncate text-sm font-semibold text-gray-800 dark:text-white/90"
                      title={db.name}
                    >
                      {db.name}
                    </p>
                    <ul className="space-y-1 text-xs text-gray-600 dark:text-gray-300">
                      {db.tables.map((table) => (
                        <li
                          key={table}
                          title={table}
                          className="truncate rounded-md bg-white px-2 py-1 dark:bg-gray-900"
                        >
                          {table}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}

          {leftOpen && (
            <ResizeHandle onMouseDown={() => setResizeSide("left")} />
          )}

          <section
            ref={centerSectionRef}
            className="flex min-w-0 flex-1 flex-col"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 px-4 py-2 dark:border-gray-800">
              <div className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-white/90">
                {centerView === "flow" ? <GitBranch size={16} /> : <ClipboardList size={16} />}
                {centerView === "flow"
                  ? "Flujo Multi-Agente (React Flow)"
                  : "Dashboard Operativo"}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="inline-flex rounded-xl border border-gray-200 bg-gray-100 p-1 dark:border-gray-700 dark:bg-gray-800">
                  <button
                    type="button"
                    onClick={() => setCenterView("flow")}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                      centerView === "flow"
                        ? "bg-white text-gray-900 shadow-sm dark:bg-gray-900 dark:text-white"
                        : "text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white"
                    }`}
                  >
                    React Flow
                  </button>
                  <button
                    type="button"
                    onClick={() => setCenterView("dashboard")}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                      centerView === "dashboard"
                        ? "bg-white text-gray-900 shadow-sm dark:bg-gray-900 dark:text-white"
                        : "text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white"
                    }`}
                  >
                    Dashboard
                  </button>
                </div>
                {!leftOpen && (
                  <button
                    onClick={openLeftPanel}
                    className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                  >
                    <PanelLeftOpen size={14} />
                    Abrir BD
                  </button>
                )}
                {!rightOpen && (
                  <button
                    onClick={openRightPanel}
                    className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                  >
                    <PanelRightOpen size={14} />
                    Abrir Chat
                  </button>
                )}
              </div>
            </div>

            <div className="relative flex min-h-0 flex-1 flex-col">
              <div className="relative min-h-0 flex-1 p-4">
                {centerView === "flow" ? (
                  <IADevFlowCanvas
                    activeNodeIds={activeNodeIds}
                    serviceAreas={SERVICE_AREAS.map((area) => area.id)}
                    availableAgents={AVAILABLE_AGENTS}
                    activeArea={activeArea}
                    activeAgent={activeAgent}
                  />
                ) : (
                  <div className="h-full overflow-hidden rounded-[24px] border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-950">
                    <DashboardPanel
                      mode="dev"
                      snapshot={dashboardSnapshot}
                      liveSnapshot={liveDashboardSnapshot}
                      historyEntries={dashboardEntries.map((entry) => ({
                        messageId: entry.messageId,
                        label: entry.label,
                        shortLabel: entry.shortLabel,
                      }))}
                      selectedMessageId={resolvedSelectedDashboardMessageId}
                      selectedMessageLabel={selectedDashboardLabel}
                      canSelectPrevious={selectedDashboardIndex > 0}
                      canSelectNext={
                        selectedDashboardIndex >= 0 &&
                        selectedDashboardIndex < dashboardEntries.length - 1
                      }
                      onSelectPrevious={() => {
                        if (selectedDashboardIndex <= 0) return;
                        selectDashboardMessage(
                          dashboardEntries[selectedDashboardIndex - 1].messageId,
                        );
                      }}
                      onSelectNext={() => {
                        if (
                          selectedDashboardIndex < 0 ||
                          selectedDashboardIndex >= dashboardEntries.length - 1
                        ) {
                          return;
                        }
                        selectDashboardMessage(
                          dashboardEntries[selectedDashboardIndex + 1].messageId,
                        );
                      }}
                      onSelectMessage={selectDashboardMessage}
                      onLoadDemo={() => undefined}
                      onCopyReport={() => {
                        void copyTextToClipboard(
                          dashboardSnapshot.executiveSummary ||
                            dashboardSnapshot.summary,
                          "Informe copiado al portapapeles.",
                        );
                      }}
                    />
                  </div>
                )}

                {terminalDetached && (
                  <div className="pointer-events-none absolute inset-x-4 bottom-4 z-30 flex justify-end">
                    <div className="pointer-events-auto h-[320px] w-full max-w-[920px]">
                      {renderTerminalPanel(true)}
                    </div>
                  </div>
                )}
              </div>

              {!terminalDetached && (
                <>
                  <div className="mx-4 mb-1 flex items-center justify-center">
                    <button
                      type="button"
                      onMouseDown={() => setResizingTerminal(true)}
                      className="inline-flex items-center gap-1 rounded-md border border-gray-700/60 bg-slate-900/80 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
                      title="Redimensionar terminal"
                    >
                      <GripHorizontal size={12} />
                      terminal
                    </button>
                  </div>
                  <div
                    className="mx-4 mb-4"
                    style={{
                      height: terminalHeight,
                      minHeight: TERMINAL_MIN_HEIGHT,
                    }}
                  >
                    {renderTerminalPanel(false)}
                  </div>
                </>
              )}
            </div>
          </section>

          {rightOpen && (
            <ResizeHandle onMouseDown={() => setResizeSide("right")} />
          )}

          {rightOpen ? (
            <aside
              className="flex shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950"
              style={{ width: rightWidth }}
            >
              <div className="flex items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-800">
                <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-gray-800 dark:text-white/90">
                  <MessageSquare size={16} />
                  <span className="truncate">Chat IA</span>
                </div>
                <div className="flex items-center gap-1">
                  {sessionId && (
                    <button
                      onClick={clearSessionMemory}
                      className="rounded-md p-1 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                      title="Reiniciar memoria"
                      disabled={isSubmitting}
                    >
                      <RotateCcw size={14} />
                    </button>
                  )}
                  <button
                    onClick={reduceRightPanel}
                    className="rounded-md p-1 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                    title="Reducir"
                  >
                    <Minus size={14} />
                  </button>
                  <button
                    onClick={expandRightPanel}
                    className="rounded-md p-1 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                    title="Ampliar"
                  >
                    <Plus size={14} />
                  </button>
                  <button
                    onClick={() => setRightOpen(false)}
                    className="rounded-md p-1 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                    title="Contraer"
                  >
                    <PanelRightClose size={16} />
                  </button>
                </div>
              </div>

              <div className="border-b border-gray-200 px-4 py-4 dark:border-gray-800">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-semibold text-gray-950 dark:text-white">
                      <Bot size={16} />
                      Chat conversacional
                    </div>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                      El chat hereda las capacidades del panel avanzado y deja el dashboard listo para inspeccionarlo a la izquierda.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <TaskStatusBadge
                      label={dashboardSnapshot.taskStatusLabel}
                      tone={dashboardSnapshot.taskStatusTone}
                    />
                    <button
                      type="button"
                      onClick={() => setCenterView("dashboard")}
                      className="rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
                    >
                      Abrir dashboard
                    </button>
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-between gap-2">
                  <p className="truncate text-sm text-gray-500 dark:text-gray-400">
                    {effectiveChatStatus}
                  </p>
                  <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                    <Cpu size={10} />
                    {transportLabel}
                  </span>
                </div>

                {semanticHint ? (
                  <div className="mt-3 rounded-2xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100">
                    {semanticHint}
                  </div>
                ) : null}

                {clarificationQuestion ? (
                  <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
                    <span className="font-semibold">Hace falta una precision:</span>{" "}
                    {clarificationQuestion}
                  </div>
                ) : null}
              </div>

              <IADevMemoryPanel
                latestCandidates={latestMemoryCandidates}
                latestPendingProposals={latestPendingProposals}
                latestActions={latestMemoryActions}
                isBusy={isSubmitting}
                onStatusChange={setChatStatus}
              />

              <div className="relative min-h-0 flex-1">
                <div ref={chatScrollRef} className="h-full overflow-auto px-4 py-4">
                  <div className="space-y-4 pb-6">
                    {hasCollapsedMessages && (
                      <div className="flex justify-center">
                        <button
                          type="button"
                          onClick={() =>
                            setMessageWindowSize((prev) =>
                              Math.min(messages.length, prev + 80),
                            )
                          }
                          className="rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                        >
                          Cargar mensajes anteriores (
                          {messages.length - visibleMessages.length})
                        </button>
                      </div>
                    )}

                    <MessageList
                      mode="dev"
                      messages={visibleMessages}
                      isBusy={isSubmitting}
                      activeDashboardMessageId={resolvedSelectedDashboardMessageId}
                      onActionClick={(action) => {
                        void handleActionClick(action);
                      }}
                      onShowDashboard={selectDashboardMessage}
                      onCopyMessage={copyAssistantMessageById}
                      onPrepareRelatedQuery={prepareRelatedQuery}
                    />
                  </div>
                </div>

                {showScrollButton && (
                  <ScrollToBottomButton
                    onClick={onScrollToBottomClick}
                    unreadCount={unreadCount}
                  />
                )}
              </div>

              <MessageInput
                value={chatInput}
                attachments={composerAttachments.map((attachment) =>
                  toAttachmentSummary(attachment),
                )}
                disabled={isSubmitting}
                isGenerating={Boolean(streamingMessageId)}
                resetSignal={composerResetSignal}
                onChange={setChatInputTracked}
                onFilesAdded={addComposerFiles}
                onRemoveAttachment={removeComposerAttachment}
                onClearAttachments={clearComposerAttachments}
                onSubmit={() => {
                  void submitChat();
                }}
                onNavigateHistory={(direction) => {
                  setChatInputTracked(navigate(direction, chatInput));
                }}
                onUndo={undoChatInput}
                onRedo={redoChatInput}
              />
            </aside>
          ) : (
            <aside className="flex w-12 shrink-0 items-start justify-center border-l border-gray-200 bg-gray-50 pt-3 dark:border-gray-800 dark:bg-gray-900">
              <button
                onClick={openRightPanel}
                title="Abrir chat"
                className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-white text-gray-700 hover:bg-gray-100 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                <PanelRightOpen size={16} />
              </button>
            </aside>
          )}
        </div>
      </div>
    </div>
  );
};

export default IADevWorkspace;
