"use client";

import type { ChatAttachmentSummary } from "@/modules/programacion/ia-dev/chat/types";
import ChatComposer from "@/modules/programacion/ia-dev/chat/components/ChatComposer";

type MessageInputProps = {
  value: string;
  attachments: ChatAttachmentSummary[];
  disabled?: boolean;
  isGenerating?: boolean;
  resetSignal?: number;
  onChange: (value: string) => void;
  onFilesAdded: (files: File[]) => void;
  onRemoveAttachment: (attachmentId: string) => void;
  onClearAttachments: () => void;
  onSubmit: () => void;
  onNavigateHistory: (direction: "up" | "down") => void;
  onUndo: () => void;
  onRedo: () => void;
};

const MessageInput = (props: MessageInputProps) => {
  return (
    <div className="sticky bottom-0 z-10 bg-gradient-to-t from-white via-white/95 to-white/70 px-3 pb-3 dark:from-gray-950 dark:via-gray-950/95 dark:to-gray-950/70">
      <ChatComposer {...props} />
    </div>
  );
};

export default MessageInput;
