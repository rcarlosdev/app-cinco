"use client";

import ChatComposer from "@/modules/programacion/ia-dev/chat/components/ChatComposer";

type MessageInputProps = {
  value: string;
  disabled?: boolean;
  isGenerating?: boolean;
  resetSignal?: number;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onNavigateHistory: (direction: "up" | "down") => void;
  onUndo: () => void;
  onRedo: () => void;
};

const MessageInput = (props: MessageInputProps) => {
  return (
    <div className="sticky bottom-0 z-10 bg-white/95 backdrop-blur dark:bg-gray-950/95">
      <ChatComposer {...props} />
    </div>
  );
};

export default MessageInput;
