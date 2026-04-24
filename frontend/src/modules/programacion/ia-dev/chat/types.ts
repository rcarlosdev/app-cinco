import type {
  IADevAction,
  IADevChartPayload,
  IADevChatResponse,
  IADevMemoryCandidate,
  IADevMemoryProposal,
} from "@/services/ia-dev.service";

export type ChatRole = "user" | "assistant";
export type ChatMessageStatus = "streaming" | "final" | "error";

export type NormalizedKPI = {
  key: string;
  label: string;
  value: number | string;
  rawValue: number | string;
};

export type NormalizedTable = {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  rowcount: number;
};

export type NormalizedHighlight = {
  label: string;
  value: number;
  share?: number;
};

export type NormalizedAssistantPayload = {
  kind: "analytics_response" | "text_response" | "error_response";
  summary: string;
  kpis: NormalizedKPI[];
  insights: string[];
  chart: IADevChartPayload | null;
  charts: IADevChartPayload[];
  table: NormalizedTable | null;
  labels: string[];
  series: number[];
  meta: Record<string, unknown>;
  hasStructuredContent: boolean;
  highlight: NormalizedHighlight | null;
};

export type ChatMessageModel = {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: number;
  status: ChatMessageStatus;
  response?: Partial<IADevChatResponse>;
  normalized?: NormalizedAssistantPayload | null;
  actions?: IADevAction[];
  memoryCandidates?: IADevMemoryCandidate[];
  pendingProposals?: IADevMemoryProposal[];
  error?: string;
};

export type ChartSourcePayload = {
  labels?: unknown[];
  series?: unknown[];
  table?: NormalizedTable | null;
  chart?: IADevChartPayload | null;
  charts?: IADevChartPayload[];
  meta?: Record<string, unknown>;
};

export type ChatSubmitStreamCallbacks = {
  onStart?: () => void;
  onChunk?: (chunk: string) => void;
  onProgress?: (response: Partial<IADevChatResponse>) => void;
};
