import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import type {
  IADevChartPayload,
  IADevChatResponse,
} from "@/services/ia-dev.service";
import type {
  NormalizedAssistantPayload,
  NormalizedKPI,
  NormalizedTable,
} from "@/modules/programacion/ia-dev/chat/types";

export type DashboardWidgetType = "kpi" | "chart" | "table" | "insights";

export type DashboardTableTab = {
  id: string;
  label: string;
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
    };

export type DashboardSnapshot = {
  sourceMessage: ChatMessageModel | null;
  response: Partial<IADevChatResponse> | null;
  payload: NormalizedAssistantPayload | null;
  widgets: DashboardWidget[];
  summary: string;
  intent: string;
  domain: string;
  selectedAgent: string;
  isLoading: boolean;
  hasStructuredContent: boolean;
};
