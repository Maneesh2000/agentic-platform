"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowUp, AudioLines, Paperclip, Plus, Square, X } from "lucide-react";
import type { Attachment } from "@/lib/chatClient";

/**
 * The ChatGPT-style composer pill: [+] menu · input · voice orb / send.
 * Send appears only when there's text; the blue orb enters voice mode.
 */
export function Composer({
  draft,
  onDraft,
  onSend,
  onStop,
  busy,
  disabled,
  attachments,
  uploading,
  onAttach,
  onRemoveAttachment,
  onVoice,
  autoFocus,
}: {
  draft: string;
  onDraft: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  busy: boolean;
  disabled: boolean;
  attachments: Attachment[];
  uploading: boolean;
  onAttach: (files: FileList | null) => void;
  onRemoveAttachment: (id: string) => void;
  onVoice: () => void;
  autoFocus?: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (busy || disabled || !draft.trim()) return;
    onSend();
  };

  return (
    <div className="w-full">
      {attachments.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-2" aria-label="Attachments">
          {attachments.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-1.5 rounded-full bg-elevated py-1 pl-3 pr-1.5 text-xs text-second"
            >
              <Paperclip size={12} aria-hidden />
              <span className="max-w-[16rem] truncate">{a.filename}</span>
              <button
                type="button"
                onClick={() => onRemoveAttachment(a.id)}
                aria-label={`Remove ${a.filename}`}
                className="rounded-full p-0.5 text-muted transition hover:text-body"
              >
                <X size={12} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      <form
        onSubmit={submit}
        className="relative flex items-center gap-1 rounded-[28px] bg-input py-2 pl-2 pr-2 shadow-[0_0_0_1px_rgba(255,255,255,0.05)]"
      >
        {/* + menu */}
        <div ref={menuRef} className="relative">
          {menuOpen && (
            <div
              role="menu"
              className="absolute bottom-full left-0 mb-3 w-72 overflow-hidden rounded-2xl border border-edge bg-elevated py-1.5 shadow-2xl"
            >
              <button
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  fileRef.current?.click();
                }}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-sm transition hover:bg-hover"
              >
                <Paperclip size={16} aria-hidden className="text-second" />
                <span>
                  Add files
                  <span className="ml-2 text-muted">txt, md, pdf, html</span>
                </span>
              </button>
            </div>
          )}
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            disabled={disabled}
            aria-label="Add files"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            className="flex h-9 w-9 items-center justify-center rounded-full text-second transition hover:bg-hover hover:text-body disabled:opacity-40"
          >
            <Plus size={18} aria-hidden />
          </button>
        </div>

        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".txt,.md,.pdf,.html,.htm"
          onChange={(e) => onAttach(e.target.files)}
          className="hidden"
        />

        <input
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          placeholder={uploading ? "Uploading…" : "Ask anything"}
          aria-label="Message"
          disabled={disabled}
          autoFocus={autoFocus}
          className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-[15px] outline-none placeholder:text-muted disabled:opacity-50"
        />

        {busy ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-body text-surface transition hover:opacity-90"
          >
            <Square size={13} aria-hidden fill="currentColor" />
          </button>
        ) : draft.trim() ? (
          <button
            type="submit"
            disabled={disabled}
            aria-label="Send message"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-body text-surface transition hover:opacity-90 disabled:opacity-40"
          >
            <ArrowUp size={18} aria-hidden />
          </button>
        ) : (
          <button
            type="button"
            onClick={onVoice}
            disabled={disabled}
            aria-label="Start voice mode"
            title="Start voice mode"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-white transition hover:brightness-110 disabled:opacity-40"
          >
            <AudioLines size={17} aria-hidden />
          </button>
        )}
      </form>
    </div>
  );
}
