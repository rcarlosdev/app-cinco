import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import type {
  IADevChartPayload,
  IADevChatResponse,
  IADevDashboardComposition,
  IADevSemanticExplanation,
} from "@/services/ia-dev.service";
import type {
  NormalizedAssistantPayload,
  NormalizedKPI,
  NormalizedTable,
} from "@/modules/programacion/ia-dev/chat/types";

export type AgenteIAViewMode = "user" | "dev";

export type DashboardWidgetType =
  | "kpi"
  | "chart"
  | "table"
  | "insights"
  | "semantic_explanation";

export type DashboardTaskStatusTone =
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "info";

export type DashboardLifecycleStage =
  | "idle"
  | "preparing"
  | "routing"
  | "planning"
  | "executing_tools"
  | "waiting_approval"
  | "streaming_evidence"
  | "completed"
  | "failed"
  | "partial";

export type DashboardSupportItem = {
  key: string;
  label: string;
  detail?: string;
};

export type DashboardTimelineStep = {
  step: string;
  state: string;
  detail?: string;
};

export type DashboardBackgroundJob = {
  status: string;
  backgroundRunId: string;
  jobId: string;
  rowsProcessed: number;
  totalEstimated: number;
  percentage: number;
  phase: string;
  phaseLabel?: string;
  elapsedSeconds: number;
  etaSeconds?: number;
  currentChunk: number;
  totalChunks: number;
  activeChunk?: number;
  serialsUniqueTotal?: number;
  serialsProcessed?: number;
  serialsPending?: number;
  stageSerialsTotal?: number;
  stageSerialsProcessed?: number;
  stageSerialsPending?: number;
  tableLabel?: string;
  tableSerialsTotal?: number;
  tableSerialsPending?: number;
  tableChunkTotal?: number;
  foundSoFar: number;
  notFoundSoFar: number;
  movilSoFar: number;
  enrichedResponsibleSoFar: number;
  foundInBaseActual?: number;
  foundInAsociadosActual?: number;
  foundInHistorico?: number;
  attachmentName?: string;
  artifactId?: string;
  resultKind?: string;
  resultLabel?: string;
  failureReason?: string;
  updatedAt?: number;
};

export type DashboardTableTab = {
  id: string;
  label: string;
  badges: string[];
  table: NormalizedTable;
};

export type DashboardWidget =
  | {
      id: string;
      type: "kpi";
      title: string;
      data: {
        items: NormalizedKPI[];
      };
    }
  | {
      id: string;
      type: "chart";
      title: string;
      data: {
        charts: IADevChartPayload[];
      };
    }
  | {
      id: string;
      type: "table";
      title: string;
      data: {
        tabs: DashboardTableTab[];
      };
    }
  | {
      id: string;
      type: "insights";
      title: string;
      data: {
        items: string[];
      };
    }
  | {
      id: string;
      type: "semantic_explanation";
      title: string;
      data: {
        explanation: IADevSemanticExplanation;
      };
    };

export type DashboardSnapshot = {
  sourceMessage: ChatMessageModel | null;
  response: Partial<IADevChatResponse> | null;
  payload: NormalizedAssistantPayload | null;
  widgets: DashboardWidget[];
  messageId: string | null;
  messageCreatedAt: number | null;
  summary: string;
  executiveSummary: string;
  intent: string;
  domain: string;
  selectedAgent: string;
  taskStatus: string;
  taskStatusLabel: string;
  taskStatusTone: DashboardTaskStatusTone;
  taskPreparationLabel: string;
  taskTimeline: DashboardTimelineStep[];
  backgroundJob: DashboardBackgroundJob | null;
  toolsUsed: DashboardSupportItem[];
  capabilitiesUsed: DashboardSupportItem[];
  approvals: DashboardSupportItem[];
  backgroundRuns: DashboardSupportItem[];
  clarificationQuestion: string;
  limitations: string[];
  evidenceSummary: Record<string, unknown>;
  validationSummary: Record<string, unknown>;
  isLoading: boolean;
  isTerminal: boolean;
  hasStructuredContent: boolean;
  semanticExplanation: IADevSemanticExplanation | null;
  dashboardComposition: IADevDashboardComposition | null;
  lifecycleStage: DashboardLifecycleStage;
  lifecycleLabel: string;
  stageDetail: string;
};
