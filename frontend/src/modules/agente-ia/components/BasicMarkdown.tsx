"use client";

import { Fragment, type ReactNode } from "react";

type BasicMarkdownProps = {
  content: string;
  className?: string;
};

const renderInline = (text: string): ReactNode[] => {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let lastIndex = 0;

  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      parts.push(text.slice(lastIndex, index));
    }

    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(
        <strong key={`${index}-bold`} className="font-semibold">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(
        <code
          key={`${index}-code`}
          className="rounded bg-black/5 px-1.5 py-0.5 font-mono text-[0.95em] dark:bg-white/10"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("*") && token.endsWith("*")) {
      parts.push(
        <em key={`${index}-italic`} className="italic">
          {token.slice(1, -1)}
        </em>,
      );
    }

    lastIndex = index + token.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
};

const BasicMarkdown = ({ content, className = "" }: BasicMarkdownProps) => {
  const blocks = content.replace(/\r\n/g, "\n").split("```");

  return (
    <div className={`space-y-3 ${className}`.trim()}>
      {blocks.map((block, index) => {
        if (index % 2 === 1) {
          return (
            <pre
              key={`code-${index}`}
              className="overflow-x-auto rounded-2xl border border-black/10 bg-slate-950 px-4 py-3 text-xs leading-6 text-slate-100"
            >
              <code>{block.trim()}</code>
            </pre>
          );
        }

        const lines = block
          .split("\n")
          .map((line) => line.trimEnd())
          .filter((line, lineIndex, array) => {
            if (line.length > 0) return true;
            const previous = array[lineIndex - 1];
            return Boolean(previous && previous.length > 0);
          });

        const children: ReactNode[] = [];
        let cursor = 0;

        while (cursor < lines.length) {
          const line = lines[cursor].trim();
          if (!line) {
            cursor += 1;
            continue;
          }

          if (/^#{1,3}\s/.test(line)) {
            const level = line.match(/^#+/)?.[0].length ?? 1;
            const text = line.replace(/^#{1,3}\s/, "");
            const Tag = level === 1 ? "h1" : level === 2 ? "h2" : "h3";
            children.push(
              <Tag
                key={`heading-${cursor}`}
                className="text-sm font-semibold text-current"
              >
                {renderInline(text)}
              </Tag>,
            );
            cursor += 1;
            continue;
          }

          if (/^([-*])\s+/.test(line)) {
            const items: string[] = [];
            while (cursor < lines.length && /^([-*])\s+/.test(lines[cursor].trim())) {
              items.push(lines[cursor].trim().replace(/^([-*])\s+/, ""));
              cursor += 1;
            }
            children.push(
              <ul key={`ul-${cursor}`} className="list-disc space-y-1 pl-5">
                {items.map((item, itemIndex) => (
                  <li key={`ul-item-${itemIndex}`}>{renderInline(item)}</li>
                ))}
              </ul>,
            );
            continue;
          }

          if (/^\d+\.\s+/.test(line)) {
            const items: string[] = [];
            while (cursor < lines.length && /^\d+\.\s+/.test(lines[cursor].trim())) {
              items.push(lines[cursor].trim().replace(/^\d+\.\s+/, ""));
              cursor += 1;
            }
            children.push(
              <ol key={`ol-${cursor}`} className="list-decimal space-y-1 pl-5">
                {items.map((item, itemIndex) => (
                  <li key={`ol-item-${itemIndex}`}>{renderInline(item)}</li>
                ))}
              </ol>,
            );
            continue;
          }

          const paragraph: string[] = [line];
          cursor += 1;
          while (
            cursor < lines.length &&
            lines[cursor].trim() &&
            !/^#{1,3}\s/.test(lines[cursor].trim()) &&
            !/^([-*])\s+/.test(lines[cursor].trim()) &&
            !/^\d+\.\s+/.test(lines[cursor].trim())
          ) {
            paragraph.push(lines[cursor].trim());
            cursor += 1;
          }

          children.push(
            <p key={`p-${cursor}`} className="whitespace-pre-wrap">
              {renderInline(paragraph.join(" "))}
            </p>,
          );
        }

        return <Fragment key={`block-${index}`}>{children}</Fragment>;
      })}
    </div>
  );
};

export default BasicMarkdown;
