"use client";

import { useEffect, useRef } from "react";
import { Markdown } from "@/components/Markdown";

export interface Bubble {
  id: string;
  text: string;
  isUser: boolean;
}

/**
 * ChatGPT-style conversation: user messages are compact right-aligned
 * bubbles; assistant replies are plain full-width text. Presentational only
 * — voice feeds it from LiveKit hooks, text from the SSE stream.
 *
 * `thinking` renders the three-dot indicator between the user's message and
 * the first streamed token — silence with no feedback reads as broken.
 */
export function MessageList({
  items,
  markdown = false,
  status,
  thinking = false,
  loading = false,
  empty,
}: {
  items: Bubble[];
  markdown?: boolean;
  status?: string | null;
  thinking?: boolean;
  loading?: boolean;
  empty?: string;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items, status, thinking]);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6">
        {loading && (
          <div className="space-y-6 pt-2" aria-hidden>
            <div className="ml-auto h-9 w-2/5 animate-pulse rounded-3xl bg-white/[0.07]" />
            <div className="space-y-2">
              <div className="h-4 w-11/12 animate-pulse rounded bg-white/[0.07]" />
              <div className="h-4 w-3/4 animate-pulse rounded bg-white/[0.07]" />
              <div className="h-4 w-1/2 animate-pulse rounded bg-white/[0.07]" />
            </div>
          </div>
        )}

        {!loading && items.length === 0 && !thinking && !status && empty && (
          <p className="pt-16 text-center text-sm text-muted">{empty}</p>
        )}

        {!loading &&
          items.map((item) =>
            item.isUser ? (
              <div key={item.id} className="flex justify-end">
                <div className="max-w-[70%] whitespace-pre-wrap rounded-3xl bg-elevated px-4 py-2.5 text-[15px] leading-relaxed">
                  {item.text}
                </div>
              </div>
            ) : (
              <div key={item.id} className="text-[15px] leading-7 text-body">
                {markdown ? <Markdown>{item.text}</Markdown> : item.text}
              </div>
            ),
          )}

        {status && (
          <p className="flex items-center gap-2 text-sm text-second">
            <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
            {status}
          </p>
        )}

        {thinking && !status && (
          <div className="flex gap-1.5 pt-1" role="status" aria-label="Assistant is thinking">
            <span className="dot h-2 w-2 rounded-full bg-second" />
            <span className="dot h-2 w-2 rounded-full bg-second" />
            <span className="dot h-2 w-2 rounded-full bg-second" />
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
