"use client";

import type { ReactNode } from "react";

type PanelToggleButtonProps = {
  label: string;
  ariaLabel: string;
  onClick: () => void;
  active?: boolean;
  children: ReactNode;
  className?: string;
};

const PanelToggleButton = ({
  label,
  ariaLabel,
  onClick,
  active = false,
  children,
  className = "",
}: PanelToggleButtonProps) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={ariaLabel}
    aria-pressed={active}
    className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${
      active
        ? "border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/30 dark:bg-sky-500/10 dark:text-sky-200"
        : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
    } ${className}`}
  >
    {children}
    <span>{label}</span>
  </button>
);

export default PanelToggleButton;
