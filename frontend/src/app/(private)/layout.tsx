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

  // Dynamic class for main content margin based on sidebar state
  const mainContentMargin = isMobileOpen
    ? "ml-0"
    : isExpanded
      ? "lg:ml-[290px]"
      : "lg:ml-[90px]";

  return (
    <RequireAuth>
      <div className="min-h-screen overflow-x-hidden xl:flex">
        {/* Sidebar and Backdrop */}
        <AppSidebar />
        <Backdrop />
        {/* Main Content Area */}
        <div
          className={`min-w-0 flex-1 overflow-x-hidden transition-all duration-300 ease-in-out ${mainContentMargin}`}
        >
          {/* Header */}
          <AppHeader />
          {/* Page Content */}
          <div
            className={
              isWideWorkspaceView
                ? "w-full min-w-0 max-w-none overflow-x-hidden p-0"
                : "mx-auto w-full min-w-0 max-w-(--breakpoint-2xl) overflow-x-hidden p-4 md:p-6"
            }
          >
            {children}
          </div>
        </div>
      </div>
    </RequireAuth>
  );
}
