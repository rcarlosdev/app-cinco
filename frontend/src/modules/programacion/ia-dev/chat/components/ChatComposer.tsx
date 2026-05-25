"use client";

import {
  FileText,
  ImageIcon,
  Loader2,
  Paperclip,
  Plus,
  SendHorizonal,
  X,
} from "lucide-react";
import {
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import type {
  ChatAttachmentSummary,
} from "@/modules/programacion/ia-dev/chat/types";
import ResizableComposer from "@/modules/programacion/ia-dev/chat/components/ResizableComposer";

type ChatComposerProps = {
  value: string;
  attachments?: ChatAttachmentSummary[];
  disabled?: boolean;
  isGenerating?: boolean;
  resetSignal?: number;
  onChange: (value: string) => void;
  onFilesAdded?: (files: File[]) => void;
  onRemoveAttachment?: (attachmentId: string) => void;
  onClearAttachments?: () => void;
  onSubmit: () => void;
  onNavigateHistory: (direction: "up" | "down") => void;
  onUndo: () => void;
  onRedo: () => void;
};

const formatFileSize = (size: number) => {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

const ChatComposer = ({
  value,
  attachments = [],
  disabled = false,
  isGenerating = false,
  resetSignal = 0,
  onChange,
  onFilesAdded,
  onRemoveAttachment,
  onClearAttachments,
  onSubmit,
  onNavigateHistory,
  onUndo,
  onRedo,
}: ChatComposerProps) => {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);

  const canAttachFiles = Boolean(onFilesAdded);
  const isSendDisabled = disabled || !value.trim();
  const attachmentLabel = useMemo(() => {
    if (attachments.length === 0) return "";
    if (attachments.length === 1) return "1 adjunto listo";
    return `${attachments.length} adjuntos listos`;
  }, [attachments.length]);

  const openFilePicker = () => {
    if (disabled || !canAttachFiles) return;
    inputRef.current?.click();
  };

  const appendFiles = (files: FileList | File[]) => {
    const nextFiles = Array.from(files).filter((file) => file.size > 0);
    if (nextFiles.length === 0) return;
    onFilesAdded?.(nextFiles);
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      appendFiles(event.target.files);
    }
    event.target.value = "";
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const isModifier = event.ctrlKey || event.metaKey;
    const target = event.currentTarget;
    const isEnter = event.key === "Enter";
    const isArrowUp = event.key === "ArrowUp";
    const isArrowDown = event.key === "ArrowDown";
    const key = event.key.toLowerCase();

    if (isModifier && key === "z" && !event.shiftKey) {
      event.preventDefault();
      onUndo();
      return;
    }

    if (isModifier && (key === "y" || (key === "z" && event.shiftKey))) {
      event.preventDefault();
      onRedo();
      return;
    }

    if (isEnter && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
      return;
    }

    if (
      isArrowUp &&
      !event.shiftKey &&
      !event.altKey &&
      target.selectionStart === 0 &&
      target.selectionEnd === 0
    ) {
      event.preventDefault();
      onNavigateHistory("up");
      return;
    }

    if (
      isArrowDown &&
      !event.shiftKey &&
      !event.altKey &&
      target.selectionStart === target.value.length &&
      target.selectionEnd === target.value.length
    ) {
      event.preventDefault();
      onNavigateHistory("down");
    }
  };

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (disabled || !canAttachFiles) return;
    setIsDraggingFiles(true);
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (disabled || !canAttachFiles) return;
    event.dataTransfer.dropEffect = "copy";
    setIsDraggingFiles(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const nextTarget = event.relatedTarget as Node | null;
    if (nextTarget && event.currentTarget.contains(nextTarget)) return;
    setIsDraggingFiles(false);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDraggingFiles(false);
    if (disabled || !canAttachFiles) return;
    if (event.dataTransfer.files?.length) {
      appendFiles(event.dataTransfer.files);
    }
  };

  return (
    <div
      className={`mx-auto w-full max-w-[980px] rounded-[28px] border bg-white/96 shadow-[0_18px_60px_rgba(15,23,42,0.10)] backdrop-blur dark:bg-gray-900/96 ${
        isDraggingFiles
          ? "border-sky-400 ring-4 ring-sky-400/15 dark:border-sky-300"
          : "border-gray-200 dark:border-gray-800"
      } relative`}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {attachments.length > 0 ? (
        <div className="border-b border-gray-200 px-4 pt-4 pb-3 dark:border-gray-800">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {attachmentLabel}
            </div>
            {onClearAttachments ? (
              <button
                type="button"
                onClick={onClearAttachments}
                className="text-xs font-medium text-gray-500 transition hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                Limpiar
              </button>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2">
            {attachments.map((attachment) => {
              const Icon =
                attachment.kind === "image" ? ImageIcon : FileText;

              return (
                <div
                  key={attachment.id}
                  className="inline-flex max-w-full items-center gap-3 rounded-2xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800/80"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-gray-600 dark:bg-gray-900 dark:text-gray-200">
                    <Icon size={16} />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-gray-800 dark:text-gray-100">
                      {attachment.name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {formatFileSize(attachment.size)}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onRemoveAttachment?.(attachment.id)}
                    className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-gray-500 transition hover:bg-white hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-200"
                    title="Quitar adjunto"
                  >
                    <X size={14} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="px-3 pt-3 pb-2">
        <ResizableComposer
          key={`composer-${resetSignal}`}
          value={value}
          onChange={onChange}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          minHeight={92}
          maxHeight={520}
          placeholder="Pregunta lo que necesites o arrastra archivos aqui..."
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-1 pb-3">
        <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={openFilePicker}
              disabled={disabled || !canAttachFiles}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-gray-200 bg-gray-50 text-gray-600 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
              title="Adjuntar archivos"
            >
            <Plus size={16} />
          </button>
            <button
              type="button"
              onClick={openFilePicker}
              disabled={disabled || !canAttachFiles}
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
              title="Adjuntar archivos"
            >
            <Paperclip size={15} />
            Adjuntar
          </button>
        </div>

        <div className="flex min-w-0 flex-1 items-center justify-end gap-3">
          <p className="hidden text-right text-[11px] leading-5 text-gray-500 md:block dark:text-gray-400">
            Enter para enviar. Shift+Enter para salto de linea. Los adjuntos se
            envian como referencia local en esta version.
          </p>
          <button
            type="button"
            onClick={onSubmit}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#111827] text-white transition hover:bg-[#1f2937] disabled:cursor-not-allowed disabled:bg-gray-300 disabled:text-white dark:bg-white dark:text-gray-950 dark:hover:bg-gray-200 dark:disabled:bg-gray-700 dark:disabled:text-gray-300"
            title="Enviar mensaje"
            disabled={isSendDisabled}
          >
            {isGenerating ? (
              <Loader2 size={17} className="animate-spin" />
            ) : (
              <SendHorizonal size={17} />
            )}
          </button>
        </div>
      </div>

      {isDraggingFiles ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-[28px] bg-sky-500/8">
          <div className="rounded-2xl border border-sky-300 bg-white/95 px-4 py-3 text-sm font-medium text-sky-700 shadow-sm dark:border-sky-400/30 dark:bg-gray-900/95 dark:text-sky-200">
            Suelta tus archivos para agregarlos al mensaje
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default ChatComposer;
