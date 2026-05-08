"use client";

import { memo } from "react";
import type { IADevAction } from "@/services/ia-dev.service";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import UserMessage from "@/modules/programacion/ia-dev/chat/components/UserMessage";
import AssistantMessage from "@/modules/programacion/ia-dev/chat/components/AssistantMessage";

type ChatMessageProps = {
  message: ChatMessageModel;
  onActionClick: (action: IADevAction) => void;
  isBusy: boolean;
  variant?: "full" | "clean";
};

const ChatMessage = ({
  message,
  onActionClick,
  isBusy,
  variant = "full",
}: ChatMessageProps) => {
  if (message.role === "user") {
    return <UserMessage message={message} />;
  }

  return (
    <AssistantMessage
      message={message}
      onActionClick={onActionClick}
      isBusy={isBusy}
      variant={variant}
    />
  );
};

export default memo(ChatMessage);
