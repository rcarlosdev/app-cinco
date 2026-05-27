"use client";

import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { Toaster as Sonner, type ToasterProps } from "sonner";

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme();

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      duration={6000}
      toastOptions={{
        classNames: {
          toast:
            "border shadow-lg backdrop-blur-md [&_[data-icon]]:mt-0.5 [&_[data-icon]]:shrink-0",
          title: "text-sm font-semibold !text-inherit",
          description: "text-sm !text-inherit opacity-90",
          success:
            "!border-success-200 !bg-success-50 !text-success-900 dark:!border-success-700 dark:!bg-success-950 dark:!text-success-50",
          error:
            "!border-error-200 !bg-error-50 !text-error-900 dark:!border-error-700 dark:!bg-error-950 dark:!text-error-50",
          warning:
            "!border-warning-200 !bg-warning-50 !text-warning-900 dark:!border-warning-700 dark:!bg-warning-950 dark:!text-warning-50",
          info:
            "!border-blue-light-200 !bg-blue-light-50 !text-blue-light-900 dark:!border-blue-light-700 dark:!bg-blue-light-950 dark:!text-blue-light-50",
        },
      }}
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
