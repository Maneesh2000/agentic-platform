"use client";

import { useCallback, useEffect, useState } from "react";
import { PanelLeftOpen } from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
import { TextChat } from "@/components/TextChat";
import { VoiceOverlay } from "@/components/VoiceOverlay";
import {
  Conversation,
  createConversation,
  deleteConversation,
  listConversations,
} from "@/lib/chatClient";

/**
 * The app shell: sidebar + conversation pane, with voice mode as a
 * fullscreen overlay (not a tab — entering and leaving voice must never
 * disturb the text thread underneath).
 */
export function ChatShell({ user }: { user: { name: string; email: string } }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [voiceOpen, setVoiceOpen] = useState(false);

  const refresh = useCallback(async () => {
    const list = await listConversations();
    setConversations(list);
    return list;
  }, []);

  const startNew = useCallback(async () => {
    const created = await createConversation();
    if (created) {
      setActiveId(created.id);
      await refresh();
    }
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const list = await refresh();
      if (cancelled) return;
      if (list.length > 0) setActiveId(list[0].id);
      else await startNew();
      setListLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [refresh, startNew]);

  const remove = useCallback(
    async (id: string) => {
      await deleteConversation(id);
      const list = await refresh();
      if (activeId === id) {
        if (list.length > 0) setActiveId(list[0].id);
        else await startNew();
      }
    },
    [activeId, refresh, startNew],
  );

  return (
    <div className="flex h-dvh bg-surface">
      {sidebarOpen && (
        <Sidebar
          conversations={conversations}
          loading={listLoading}
          activeId={activeId}
          onSelect={setActiveId}
          onNew={startNew}
          onDelete={remove}
          onCollapse={() => setSidebarOpen(false)}
          user={user}
        />
      )}

      <main className="relative flex min-w-0 flex-1 flex-col">
        {!sidebarOpen && (
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
            className="absolute left-3 top-3 z-10 rounded-lg p-2 text-second transition hover:bg-hover hover:text-body"
          >
            <PanelLeftOpen size={18} aria-hidden />
          </button>
        )}

        <TextChat
          conversationId={activeId}
          onTitleChanged={refresh}
          onVoice={() => setVoiceOpen(true)}
        />
      </main>

      {voiceOpen && <VoiceOverlay onClose={() => setVoiceOpen(false)} />}
    </div>
  );
}
