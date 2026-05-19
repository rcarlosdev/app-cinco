"use client";

import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

type ResponsiveDrawerProps = {
  open: boolean;
  side: "left" | "right";
  title: string;
  description: string;
  onClose: () => void;
  children: ReactNode;
};

const ResponsiveDrawer = ({
  open,
  side,
  title,
  description,
  onClose,
  children,
}: ResponsiveDrawerProps) => {
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  return (
    <div
      className={`absolute inset-0 z-40 xl:hidden ${open ? "pointer-events-auto" : "pointer-events-none"}`}
      aria-hidden={!open}
    >
      <button
        type="button"
        aria-label={`Cerrar ${title.toLowerCase()}`}
        onClick={onClose}
        className={`absolute inset-0 bg-slate-950/45 transition duration-300 ${
          open ? "opacity-100" : "opacity-0"
        }`}
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`absolute top-0 h-full w-[min(92vw,26rem)] max-w-full overflow-hidden border-gray-200 bg-white shadow-2xl transition duration-300 ease-out dark:border-gray-800 dark:bg-gray-950 ${
          side === "left"
            ? `left-0 border-r ${open ? "translate-x-0" : "-translate-x-full"}`
            : `right-0 border-l ${open ? "translate-x-0" : "translate-x-full"}`
        }`}
      >
        <div className="flex h-full min-h-0 flex-col">
          <header className="border-b border-gray-200 px-4 py-4 dark:border-gray-800">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-950 dark:text-white">
                  {title}
                </p>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {description}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label={`Cerrar ${title.toLowerCase()}`}
                className="rounded-full border border-gray-200 bg-white p-2 text-gray-600 transition hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
              >
                <X size={16} />
              </button>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
        </div>
      </aside>
    </div>
  );
};

export default ResponsiveDrawer;
