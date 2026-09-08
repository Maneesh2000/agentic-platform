"use client";

import { useMemo, useState } from "react";
import { PanelLeftClose, Search, SquarePen, Trash2, X } from "lucide-react";
import { AccountMenu } from "@/components/AccountMenu";
import type { Conversation } from "@/lib/chatClient";

export function Sidebar({
  conversations,
  loading,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onCollapse,
  user,
}: {
  conversations: Conversation[];
  loading: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onCollapse: () => void;
  user: { name: string; email: string };
}) {
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [conversations, query]);

  return (
    <aside className="flex h-full w-[260px] shrink-0 flex-col bg-sidebar">
      {/* header */}
      <div className="flex items-center justify-between px-3 pb-1 pt-3">
        <span className="px-2 text-sm font-semibold tracking-tight">Assistant</span>
        <div className="flex items-center">
          <button
            onClick={() => {
              setSearching((s) => !s);
              setQuery("");
            }}
            aria-label="Search chats"
            className="rounded-lg p-2 text-second transition hover:bg-hover hover:text-body"
          >
            <Search size={16} aria-hidden />
          </button>
          <button
            onClick={onCollapse}
            aria-label="Close sidebar"
            className="rounded-lg p-2 text-second transition hover:bg-hover hover:text-body"
          >
            <PanelLeftClose size={16} aria-hidden />
          </button>
        </div>
      </div>

      {/* new chat */}
      <div className="px-3 pt-1">
        <button
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm transition hover:bg-hover"
        >
          <SquarePen size={16} aria-hidden className="text-second" />
          New chat
        </button>
      </div>

      {/* search */}
      {searching && (
        <div className="px-3 pt-2">
          <div className="flex items-center gap-2 rounded-lg bg-elevated px-2.5">
            <Search size={14} aria-hidden className="shrink-0 text-muted" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search chats"
              aria-label="Search chats"
              className="w-full bg-transparent py-2 text-sm outline-none placeholder:text-muted"
            />
            {query && (
              <button onClick={() => setQuery("")} aria-label="Clear search">
                <X size={14} className="text-muted" aria-hidden />
              </button>
            )}
          </div>
        </div>
      )}

      {/* chats */}
      <nav aria-label="Chats" className="mt-4 flex-1 overflow-y-auto px-3">
        <p className="px-2 pb-1 text-xs font-medium text-muted">Chats</p>

        {loading && (
          <div className="space-y-2 px-2 pt-1" aria-hidden>
            {[0.9, 0.65, 0.8, 0.5, 0.72].map((w, i) => (
              <div
                key={i}
                className="h-4 animate-pulse rounded bg-white/[0.07]"
                style={{ width: `${w * 100}%` }}
              />
            ))}
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <p className="px-2 pt-2 text-xs text-muted">
            {query ? "No chats match." : "No chats yet."}
          </p>
        )}

        {!loading &&
          filtered.map((c) => {
            const active = c.id === activeId;
            return (
              <div
                key={c.id}
                className={`group relative flex items-center rounded-lg transition ${
                  active ? "bg-active" : "hover:bg-hover"
                }`}
              >
                <button
                  onClick={() => onSelect(c.id)}
                  aria-current={active ? "page" : undefined}
                  className="min-w-0 flex-1 truncate px-2 py-2 text-left text-sm text-body"
                >
                  {c.title}
                </button>
                <button
                  onClick={() => onDelete(c.id)}
                  aria-label={`Delete ${c.title}`}
                  className="absolute right-1 rounded p-1.5 text-muted opacity-0 transition hover:text-body focus:opacity-100 group-hover:opacity-100"
                >
                  <Trash2 size={14} aria-hidden />
                </button>
              </div>
            );
          })}
      </nav>

      {/* account */}
      <AccountMenu user={user} />
    </aside>
  );
}
