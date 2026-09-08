"use client";

import { useMemo } from "react";
import { useChat, useLocalParticipant, useTranscriptions } from "@livekit/components-react";
import { MessageList } from "@/components/MessageList";

/**
 * The in-room transcript. Agents v1.x publish transcriptions as text streams
 * (topic "lk.transcription"); `useTranscriptions` aggregates the user's STT
 * segments and the agent's speech into one ordered list, and `useChat` adds
 * anything typed into the room ("lk.chat"). The two never duplicate each
 * other, so merging by timestamp yields the whole conversation.
 *
 * Voice replies are plain text by contract (prompts/assistant.md), so this
 * renders without markdown.
 */
export function VoiceTranscript() {
  const transcriptions = useTranscriptions();
  const { chatMessages } = useChat();
  const { localParticipant } = useLocalParticipant();

  const items = useMemo(() => {
    const local = localParticipant?.identity;
    const spoken = transcriptions.map((seg) => ({
      id: seg.streamInfo.id,
      ts: seg.streamInfo.timestamp,
      text: seg.text,
      isUser: seg.participantInfo.identity === local,
    }));
    const typed = chatMessages.map((msg) => ({
      id: msg.id,
      ts: msg.timestamp,
      text: msg.message,
      isUser: !msg.from || msg.from.identity === local,
    }));
    return [...spoken, ...typed]
      .sort((a, b) => a.ts - b.ts)
      .map(({ id, text, isUser }) => ({ id, text, isUser }));
  }, [transcriptions, chatMessages, localParticipant]);

  return <MessageList items={items} empty="Say something — the conversation appears here." />;
}
