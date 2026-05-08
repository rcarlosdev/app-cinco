"use client";

import { useMemo, useState } from "react";
import { Lightbulb, ChevronDown, ChevronUp } from "lucide-react";
import {
  getSemanticTone,
  toneSoftClass,
} from "@/modules/programacion/ia-dev/chat/utils/semanticTone";

type InsightListProps = {
  insights: string[];
};

const DEFAULT_VISIBLE_INSIGHTS = 4;

const InsightList = ({ insights }: InsightListProps) => {
  const [expanded, setExpanded] = useState(false);

  const visibleInsights = useMemo(() => {
    if (expanded) return insights;
    return insights.slice(0, DEFAULT_VISIBLE_INSIGHTS);
  }, [expanded, insights]);

  if (insights.length === 0) return null;

  return (
    <section className="space-y-2">
      <p className="text-[11px] font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
        Insights
      </p>
      <ul className="space-y-2">
        {visibleInsights.map((insight, index) => (
          <li
            key={`${insight}-${index}`}
            className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-sm ${toneSoftClass[getSemanticTone({ value: insight })]}`}
          >
            <Lightbulb size={14} className="mt-0.5 shrink-0" />
            <span>{insight}</span>
          </li>
        ))}
      </ul>

      {insights.length > DEFAULT_VISIBLE_INSIGHTS && (
        <button
          type="button"
          className="text-brand-700 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200 inline-flex items-center gap-1 text-xs font-semibold"
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? (
            <>
              <ChevronUp size={12} />
              Mostrar menos insights
            </>
          ) : (
            <>
              <ChevronDown size={12} />
              Ver todos los insights ({insights.length})
            </>
          )}
        </button>
      )}
    </section>
  );
};

export default InsightList;
