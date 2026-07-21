"use client";

import { useSidebar } from "@/context/SidebarContext";
import AppHeader from "@/components/layout/AppHeader";
import AppSidebar from "@/components/layout/AppSidebar";
import Backdrop from "@/components/layout/Backdrop";
import RequireAuth from "@/components/auth/RequireAuth";
import React from "react";
import { usePathname } from "next/navigation";

type RootLayoutProps = {
  children: React.ReactNode;
};

export default function AdminLayout({ children }: RootLayoutProps) {
  const { isExpanded, isMobileOpen } = useSidebar();
  const pathname = usePathname();
  const isWideWorkspaceView =
    pathname?.startsWith("/programacion/ia-dev") ||
    pathname?.startsWith("/agente-ia") ||
    false;
  const desktopSidebarWidth = isExpanded ? "290px" : "90px";

  // Dynamic class for main content margin based on sidebar state
  const mainContentMargin = isWideWorkspaceView
    ? "ml-0"
    : isMobileOpen
      ? "ml-0"
      : isExpanded
        ? "lg:ml-[290px]"
        : "lg:ml-[90px]";

  return (
    <RequireAuth>
      <div className="flex h-screen w-full overflow-hidden bg-white dark:bg-gray-900">
        {/* Sidebar and Backdrop */}
        <AppSidebar />
        <Backdrop />
        {/* Main Content Area */}
        <div
          style={
            isWideWorkspaceView
              ? ({
                  "--workspace-sidebar-width": desktopSidebarWidth,
                } as React.CSSProperties)
              : undefined
          }
          className={`flex h-screen min-w-0 flex-1 flex-col overflow-hidden transition-all duration-300 ease-in-out ${
            isWideWorkspaceView
              ? "lg:ml-[var(--workspace-sidebar-width)] lg:w-[calc(100%-var(--workspace-sidebar-width))]"
              : mainContentMargin
          }`}
        >
          {/* Header */}
          <AppHeader />
          {/* Page Content */}
          <main
            className={
              isWideWorkspaceView
                ? "flex-1 w-full min-w-0 max-w-none overflow-y-auto overflow-x-hidden p-0"
                : "flex-1 w-full min-w-0 max-w-(--breakpoint-2xl) mx-auto overflow-y-auto overflow-x-hidden p-4 md:p-6"
            }
          >
            {children}
          </main>
        </div>
      </div>
    </RequireAuth>
  );
}
