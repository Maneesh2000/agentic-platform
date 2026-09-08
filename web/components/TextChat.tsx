"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Composer } from "@/components/Composer";
import { Bubble, MessageList } from "@/components/MessageList";
import {
  Attachment,
  fetchMessages,
  streamChat,
  uploadFile,
} from "@/lib/chatClient";

export function TextChat({
  conversationId,
  onTitleChanged,
  onVoice,
}: {
  conversationId: string | null;
  onTitleChanged: () => void;
  onVoice: () => void;
}) {
  const [items, setItems] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Switching conversations reloads history from the server — the browser
  // is never the source of truth for it.
  useEffect(() => {
    abortRef.current?.abort();
    setItems([]);
    setStatus(null);
    setBusy(false);
    setThinking(false);
    setAttachments([]);
    if (!conversationId) return;

    let cancelled = false;
    setHistoryLoading(true);
    fetchMessages(conversationId)
      .then((history) => {
        if (cancelled) return;
        setItems(
          history.map((m, i) => ({
            id: `h${i}`,
            text: m.content,
            isUser: m.role === "user",
          })),
        );
      })
      .finally(() => !cancelled && setHistoryLoading(false));
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const send = useCallback(async () => {
    const text = draft.trim();
    if (!text || !conversationId || busy) return;
    setDraft("");

    const stamp = Date.now();
    setItems((prev) => [...prev, { id: `u${stamp}`, text, isUser: true }]);
    setBusy(true);
    setThinking(true);
    setStatus(null);

    const controller = new AbortController();
    abortRef.current = controller;
    const replyId = `a${stamp}`;
    let reply = "";
    const firstUserMessage = items.length === 0;
    const sent = attachments;
    setAttachments([]);

    try {
      for await (const ev of streamChat(conversationId, text, sent, controller.signal)) {
        if (ev.type === "status") {
          setThinking(false);
          setStatus(ev.text);
        } else if (ev.type === "error") {
          setThinking(false);
          toast.error(ev.text);
        } else {
          setThinking(false);
          setStatus(null);
          reply += ev.text;
          setItems((prev) => {
            const rest = prev.filter((b) => b.id !== replyId);
            return [...rest, { id: replyId, text: reply, isUser: false }];
          });
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        toast.error(err instanceof Error ? err.message : "Something went wrong");
      }
    } finally {
      setBusy(false);
      setThinking(false);
      setStatus(null);
      abortRef.current = null;
      if (firstUserMessage) onTitleChanged();
    }
  }, [attachments, busy, conversationId, draft, items.length, onTitleChanged]);

  const attach = useCallback(async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      const added = await Promise.all(Array.from(files).map(uploadFile));
      setAttachments((prev) => [...prev, ...added]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, []);

  const composer = (autoFocus: boolean) => (
    <Composer
      draft={draft}
      onDraft={setDraft}
      onSend={send}
      onStop={() => abortRef.current?.abort()}
      busy={busy}
      disabled={!conversationId}
      attachments={attachments}
      uploading={uploading}
      onAttach={attach}
      onRemoveAttachment={(id) =>
        setAttachments((prev) => prev.filter((a) => a.id !== id))
      }
      onVoice={onVoice}
      autoFocus={autoFocus}
    />
  );

  const empty = items.length === 0 && !busy && !historyLoading;

  // Hero layout until the first message, exactly like the reference: big
  // centered heading with the composer beneath it.
  if (empty) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-4 pb-24">
        <h1 className="mb-7 text-3xl font-semibold tracking-tight">
          What&rsquo;s on your mind today?
        </h1>
        <div className="w-full max-w-3xl">{composer(true)}</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <MessageList
        items={items}
        markdown
        status={status}
        thinking={thinking}
        loading={historyLoading}
      />
      <div className="mx-auto w-full max-w-3xl px-4 pb-4">
        {composer(false)}
        <p className="pt-2 text-center text-xs text-muted">
          The assistant can make mistakes. Check important info.
        </p>
      </div>
    </div>
  );
}
