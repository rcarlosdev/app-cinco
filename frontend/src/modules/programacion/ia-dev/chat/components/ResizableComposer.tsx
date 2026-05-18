"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { GripHorizontal, RotateCcw } from "lucide-react";

type ResizableComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  placeholder?: string;
  disabled?: boolean;
  minHeight?: number;
  maxHeight?: number;
};

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const ResizableComposer = ({
  value,
  onChange,
  onKeyDown,
  placeholder = "Escribe tu consulta...",
  disabled = false,
  minHeight = 72,
  maxHeight = 260,
}: ResizableComposerProps) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const dragStartRef = useRef<{ y: number; height: number } | null>(null);
  const [manualHeight, setManualHeight] = useState<number | null>(null);
  const [autoHeight, setAutoHeight] = useState(minHeight);
  const [viewportHeight, setViewportHeight] = useState<number>(() =>
    typeof window !== "undefined" ? window.innerHeight : 900,
  );

  const dynamicMaxHeight = useMemo(
    () => clamp(Math.floor(viewportHeight * 0.4), minHeight, maxHeight),
    [maxHeight, minHeight, viewportHeight],
  );

  const effectiveHeight = useMemo(
    () => clamp(manualHeight ?? autoHeight, minHeight, dynamicMaxHeight),
    [autoHeight, dynamicMaxHeight, manualHeight, minHeight],
  );
  const shouldUseInternalScroll = effectiveHeight >= dynamicMaxHeight - 1;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea || manualHeight != null) return;
    const previousInlineHeight = textarea.style.height;
    textarea.style.height = "auto";
    const measured = clamp(textarea.scrollHeight, minHeight, dynamicMaxHeight);
    // Auto-size bidireccional: crece y reduce según contenido.
    setAutoHeight((prev) => (prev === measured ? prev : measured));
    textarea.style.height = previousInlineHeight;
  }, [dynamicMaxHeight, manualHeight, minHeight, value]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea || manualHeight == null) return;
    const previousInlineHeight = textarea.style.height;
    textarea.style.height = "auto";
    const measured = clamp(textarea.scrollHeight, minHeight, dynamicMaxHeight);
    textarea.style.height = previousInlineHeight;

    // Si el usuario dejó un alto manual pequeño, permitimos crecer para no recortar texto largo.
    if (measured > manualHeight) {
      setManualHeight(measured);
    }
  }, [dynamicMaxHeight, manualHeight, minHeight, value]);

  useEffect(() => {
    const onResize = () => {
      setViewportHeight(window.innerHeight);
    };

    window.addEventListener("resize", onResize, { passive: true });
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const startResize = useCallback(
    (event: ReactMouseEvent<HTMLButtonElement>) => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      dragStartRef.current = {
        y: event.clientY,
        height: manualHeight ?? autoHeight,
      };
      document.body.style.cursor = "row-resize";
      document.body.style.userSelect = "none";
    },
    [autoHeight, manualHeight],
  );

  useEffect(() => {
    const onMouseMove = (event: MouseEvent) => {
      if (!dragStartRef.current) return;
      const delta = event.clientY - dragStartRef.current.y;
      const nextHeight = clamp(
        dragStartRef.current.height + delta,
        minHeight,
        dynamicMaxHeight,
      );
      setManualHeight(nextHeight);
    };

    const onMouseUp = () => {
      if (!dragStartRef.current) return;
      dragStartRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [dynamicMaxHeight, minHeight]);

  return (
    <div className="relative flex-1 rounded-[22px] bg-transparent">
      <textarea
        ref={textareaRef}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        style={{ height: effectiveHeight }}
        className={`w-full resize-none bg-transparent px-4 pt-3 pb-8 text-[15px] leading-6 text-gray-800 outline-none placeholder:text-gray-400 dark:text-gray-100 dark:placeholder:text-gray-500 ${
          shouldUseInternalScroll ? "overflow-y-auto" : "overflow-y-hidden"
        }`}
      />
      <div className="pointer-events-none absolute right-2 bottom-1.5 flex items-center gap-1 text-[10px] text-gray-400 dark:text-gray-500">
        {manualHeight != null && (
          <button
            type="button"
            className="pointer-events-auto inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] hover:bg-gray-100 dark:hover:bg-gray-800"
            onClick={() => setManualHeight(null)}
            title="Volver a tamano automatico"
          >
            <RotateCcw size={10} />
            Auto
          </button>
        )}
        <button
          type="button"
          className="pointer-events-auto inline-flex items-center rounded-full px-2 py-1 hover:bg-gray-100 dark:hover:bg-gray-800"
          onMouseDown={startResize}
          title="Redimensionar compositor"
        >
          <GripHorizontal size={12} />
        </button>
      </div>
    </div>
  );
};

export default ResizableComposer;
