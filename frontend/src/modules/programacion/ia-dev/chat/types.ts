//frontend/src/modules/programacion/ia-dev/chat/types.ts
import type {
  IADevAction,
  IADevChartPayload,
  IADevChatResponse,
  IADevMemoryCandidate,
  IADevMemoryProposal,
  IADevSemanticExplanation,
} from "@/services/ia-dev.service";

export type ChatRole = "user" | "assistant";
export type ChatMessageStatus = "streaming" | "final" | "error";
export type ChatAttachmentKind = "image" | "document";

export type ChatAttachmentSummary = {
  id: string;
  name: string;
  mimeType: string;
  size: number;
  kind: ChatAttachmentKind;
};

export type NormalizedKPI = {
  key: string;
  label: string;
  value: number | string;
  rawValue: number | string;
};

export type NormalizedTable = {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  exportRows: Array<Record<string, unknown>>;
  rowcount: number;
  totalRecords: number;
  returnedRecords: number;
  exportRecords: number;
  exportTruncated: boolean;
  exportLimit: number;
  truncated: boolean;
  limit: number;
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
  extraTables: NormalizedTable[];
  labels: string[];
  series: number[];
  meta: Record<string, unknown>;
  hasStructuredContent: boolean;
  highlight: NormalizedHighlight | null;
  route: Record<string, unknown>;
  fallbackUsed: Record<string, unknown>;
  legacyUsed: boolean;
  contractPolicyApplied: Record<string, unknown>;
  needsClarification: boolean;
  blockReason: string;
  progressSource: string;
  semanticExplanation: IADevSemanticExplanation | null;
};

export type ChatMessageModel = {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: number;
  status: ChatMessageStatus;
  attachments?: ChatAttachmentSummary[];
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
