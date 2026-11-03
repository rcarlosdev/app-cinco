"use client";

import React from "react";
import { Filter, CalendarPlus, UploadCloud } from "lucide-react";

export type AgendaActiveTab = "filtro" | "agendar" | "importar";

interface AgendaHeaderTabsProps {
  activeTab: AgendaActiveTab;
  setActiveTab: (tab: AgendaActiveTab) => void;
}

export const AgendaHeaderTabs: React.FC<AgendaHeaderTabsProps> = ({
  activeTab,
  setActiveTab,
}) => {
  const tabs = [
    {
      id: "filtro" as AgendaActiveTab,
      label: "Filtros y Búsqueda",
      icon: Filter,
      color: "text-brand-600 dark:text-brand-400",
      activeBg: "bg-brand-50 text-brand-700 border-brand-600 dark:bg-brand-950/50 dark:text-brand-300 dark:border-brand-400",
    },
    {
      id: "agendar" as AgendaActiveTab,
      label: "Agendar Actividad",
      icon: CalendarPlus,
      color: "text-brand-600 dark:text-brand-400",
      activeBg: "bg-brand-50 text-brand-700 border-brand-600 dark:bg-brand-950/50 dark:text-brand-300 dark:border-brand-400",
    },
    {
      id: "importar" as AgendaActiveTab,
      label: "Importar CSV",
      icon: UploadCloud,
      color: "text-brand-600 dark:text-brand-400",
      activeBg: "bg-brand-50 text-brand-700 border-brand-600 dark:bg-brand-950/50 dark:text-brand-300 dark:border-brand-400",
    },
  ];

  return (
    <div className="flex border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-2 sm:px-4 pt-2 overflow-x-auto">
      <nav className="flex space-x-1 sm:space-x-2 min-w-max" aria-label="Tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`group inline-flex items-center px-3 sm:px-4 py-2 font-medium text-xs md:text-sm rounded-t-lg border-b-2 transition-all duration-150 whitespace-nowrap ${
                isActive
                  ? `${tab.activeBg} font-semibold shadow-sm`
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200"
              }`}
            >
              <Icon
                className={`-ml-0.5 mr-2 h-4 w-4 ${
                  isActive ? tab.color : "text-gray-400 group-hover:text-gray-500 dark:text-gray-500"
                }`}
              />
              {tab.label}
            </button>
          );
        })}
      </nav>
    </div>
  );
};
