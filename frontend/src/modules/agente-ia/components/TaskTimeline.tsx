"use client";

import type { IADevSemanticTimelineStep } from "@/services/ia-dev.service";

type TaskTimelineProps = {
  steps: IADevSemanticTimelineStep[];
};

const stateStyles: Record<string, string> = {
  blocked: "border-amber-200 bg-amber-50 text-amber-700",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-700",
  current: "border-amber-200 bg-amber-50 text-amber-700",
  failed: "border-red-200 bg-red-50 text-red-700",
  pending: "border-gray-200 bg-gray-50 text-gray-500",
  awaiting_approval: "border-amber-200 bg-amber-50 text-amber-700",
  executing: "border-sky-200 bg-sky-50 text-sky-700",
};

const toLabel = (value: string) =>
  value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const TaskTimeline = ({ steps }: TaskTimelineProps) => {
  if (steps.length === 0) return null;

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {steps.map((step) => {
        const state = step.state || "pending";
        return (
          <div
            key={`${step.step}-${state}`}
            className={`rounded-2xl border px-3 py-3 ${stateStyles[state] || stateStyles.pending}`}
          >
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em]">
              {state}
            </div>
            <div className="mt-1 text-sm font-medium">{toLabel(step.step)}</div>
            {step.detail ? (
              <div className="mt-1 text-xs opacity-80">{step.detail}</div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

export default TaskTimeline;
