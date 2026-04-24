import type { IADevChatResponse } from "@/services/ia-dev.service";

const baseMemory = {
  used_messages: 0,
  capacity_messages: 0,
  usage_ratio: 0,
  trim_events: 0,
  saturated: false,
};

const baseObservability = {
  enabled: false,
  duration_ms: 0,
  tool_latencies_ms: {},
  tokens_in: 0,
  tokens_out: 0,
  estimated_cost_usd: 0,
};

const baseReasoning = {
  enabled: true,
  version: "ia_dev.reasoning.v1",
  status: "running",
  working_goal: "",
  current_next_step: "",
  hypotheses: [],
  diagnostics: [],
  memory_summary: {},
  duration_ms: 0,
};

export const buildStreamingResponseSkeleton = (
  patch?: Partial<IADevChatResponse>,
): Partial<IADevChatResponse> => {
  const payload = patch || {};
  return {
    session_id: payload.session_id || "",
    reply: payload.reply || "",
    orchestrator: {
      ...(payload.orchestrator || {}),
    },
    data: {
      ...(payload.data || {}),
    },
    data_sources: {
      ...(payload.data_sources || {}),
    },
    trace: Array.isArray(payload.trace) ? payload.trace : [],
    memory: {
      ...baseMemory,
      ...(payload.memory || {}),
    },
    observability: {
      ...baseObservability,
      ...(payload.observability || {}),
    },
    active_nodes: Array.isArray(payload.active_nodes) ? payload.active_nodes : [],
    working_updates: Array.isArray(payload.working_updates)
      ? payload.working_updates
      : [],
    reasoning: {
      ...baseReasoning,
      ...(payload.reasoning || {}),
    },
  };
};

export const mergeStreamingResponse = (
  current: Partial<IADevChatResponse> | undefined,
  patch: Partial<IADevChatResponse> | undefined,
): Partial<IADevChatResponse> => {
  const base = buildStreamingResponseSkeleton(current);
  const next = buildStreamingResponseSkeleton(patch);
  return {
    ...base,
    ...next,
    orchestrator: {
      ...(base.orchestrator || {}),
      ...(next.orchestrator || {}),
    },
    data: {
      ...(base.data || {}),
      ...(next.data || {}),
    },
    data_sources: {
      ...(base.data_sources || {}),
      ...(next.data_sources || {}),
    },
    memory: {
      ...baseMemory,
      ...(base.memory || {}),
      ...(next.memory || {}),
    },
    observability: {
      ...baseObservability,
      ...(base.observability || {}),
      ...(next.observability || {}),
    },
    reasoning: {
      ...baseReasoning,
      ...(base.reasoning || {}),
      ...(next.reasoning || {}),
    },
    working_updates:
      next.working_updates && next.working_updates.length > 0
        ? next.working_updates
        : base.working_updates,
    trace: next.trace && next.trace.length > 0 ? next.trace : base.trace,
    active_nodes:
      next.active_nodes && next.active_nodes.length > 0
        ? next.active_nodes
        : base.active_nodes,
  };
};
