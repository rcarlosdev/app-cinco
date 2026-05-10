"use client";

type InsightCardsProps = {
  items: string[];
};

const InsightCards = ({ items }: InsightCardsProps) => {
  if (items.length === 0) return null;

  return (
    <div className="grid gap-3 xl:grid-cols-2">
      {items.map((item, index) => (
        <article
          key={`insight-${index}`}
          className="rounded-3xl border border-gray-200 bg-white px-4 py-4 shadow-sm dark:border-gray-800 dark:bg-gray-950"
        >
          <p className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
            Insight {index + 1}
          </p>
          <p className="mt-3 text-sm leading-6 text-gray-700 dark:text-gray-200">
            {item}
          </p>
        </article>
      ))}
    </div>
  );
};

export default InsightCards;
