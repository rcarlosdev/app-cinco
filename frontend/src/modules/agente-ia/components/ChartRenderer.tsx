"use client";

import IADevChartPanel from "@/modules/programacion/ia-dev/components/IADevChartPanel";
import type { IADevChartPayload } from "@/services/ia-dev.service";

type ChartRendererProps = {
  charts: IADevChartPayload[];
};

const ChartRenderer = ({ charts }: ChartRendererProps) => {
  if (charts.length === 0) return null;

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {charts.map((chart, index) => (
        <div
          key={`${chart.title || "chart"}-${index}`}
          className="rounded-[28px] border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-950"
        >
          <IADevChartPanel
            chart={chart}
            embedded
            showDetails={false}
            showHeader
          />
        </div>
      ))}
    </div>
  );
};

export default ChartRenderer;
