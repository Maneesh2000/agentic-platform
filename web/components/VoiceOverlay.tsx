"use client";

import { useCallback, useEffect, useState } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  TrackToggle,
  useVoiceAssistant,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import { Captions, X } from "lucide-react";
import { toast } from "sonner";
import { VoiceTranscript } from "@/components/VoiceTranscript";
import "@livekit/components-styles";

type Connection = { serverUrl: string; token: string };

/**
 * ChatGPT-style voice mode: a fullscreen takeover with a single animated
 * blue orb whose motion mirrors the agent's state, and two controls at the
 * bottom — mute and end. Connects on mount (entering voice mode IS the
 * intent to talk; a second "start" button would be a speed bump).
 *
 * Voice sessions are deliberately ephemeral and separate from text threads.
 */
export function VoiceOverlay({ onClose }: { onClose: () => void }) {
  const [conn, setConn] = useState<Connection | null>(null);
  const [failed, setFailed] = useState(false);

  const connect = useCallback(async () => {
    setFailed(false);
    try {
      const res = await fetch("/api/token");
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "token request failed");
      setConn(body);
    } catch (err) {
      setFailed(true);
      toast.error(err instanceof Error ? err.message : "Could not connect");
    }
  }, []);

  useEffect(() => {
    void connect();
  }, [connect]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black" role="dialog" aria-label="Voice mode">
      {failed ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-second">Could not connect to voice.</p>
          <div className="flex gap-3">
            <button
              onClick={connect}
              className="rounded-full bg-white px-5 py-2 text-sm font-medium text-black hover:bg-white/85"
            >
              Retry
            </button>
            <button
              onClick={onClose}
              className="rounded-full border border-white/20 px-5 py-2 text-sm text-second hover:text-body"
            >
              Back to chat
            </button>
          </div>
        </div>
      ) : !conn ? (
        <Centered label="Connecting…">
          <div className="orb-thinking h-28 w-28 rounded-full bg-accent/40" />
        </Centered>
      ) : (
        <LiveKitRoom
          serverUrl={conn.serverUrl}
          token={conn.token}
          connect
          audio
          video={false}
          // AEC is not optional: without echoCancellation the agent hears
          // its own voice from the speakers and interrupts itself.
          options={{
            audioCaptureDefaults: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          }}
          onDisconnected={onClose}
          onError={(err) => toast.error(err.message)}
          className="flex flex-1 flex-col"
        >
          <RoomAudioRenderer />
          <StartAudio label="Tap to enable audio" />
          <VoiceStage onClose={onClose} />
        </LiveKitRoom>
      )}
    </div>
  );
}

const ORB: Record<string, { className: string; label: string }> = {
  disconnected: { className: "bg-accent/30", label: "Agent offline" },
  connecting: { className: "orb-thinking bg-accent/40", label: "Connecting…" },
  initializing: { className: "orb-thinking bg-accent/40", label: "Agent starting…" },
  listening: { className: "orb-listening bg-accent", label: "Listening" },
  thinking: { className: "orb-thinking bg-accent", label: "Thinking…" },
  speaking: { className: "orb-speaking bg-accent", label: "" },
};

function VoiceStage({ onClose }: { onClose: () => void }) {
  const { state } = useVoiceAssistant();
  const [captions, setCaptions] = useState(false);
  const orb = ORB[state] ?? ORB.connecting;

  return (
    <>
      <Centered label={orb.label}>
        <div
          className={`h-28 w-28 rounded-full shadow-[0_0_80px_rgba(75,123,236,0.45)] ${orb.className}`}
        />
      </Centered>

      {captions && (
        <div className="mx-auto mb-4 flex h-56 w-full max-w-2xl flex-col px-4">
          <VoiceTranscript />
        </div>
      )}

      <div className="flex items-center justify-center gap-4 pb-10">
        <TrackToggle
          source={Track.Source.Microphone}
          showIcon
          aria-label="Toggle microphone"
          // ! modifiers: @livekit/components-styles .lk-button sets its own
          // background/padding and would otherwise win.
          className="flex !h-12 !w-12 items-center justify-center !rounded-full !bg-white/10 !p-0 text-body transition hover:!bg-white/20 [&_svg]:h-5 [&_svg]:w-5"
        />
        <button
          onClick={() => setCaptions((c) => !c)}
          aria-label="Toggle captions"
          aria-pressed={captions}
          className={`flex h-12 w-12 items-center justify-center rounded-full transition ${
            captions ? "bg-white text-black" : "bg-white/10 text-body hover:bg-white/20"
          }`}
        >
          <Captions size={20} aria-hidden />
        </button>
        <button
          onClick={onClose}
          aria-label="End voice mode"
          className="flex h-12 w-12 items-center justify-center rounded-full bg-white/10 text-body transition hover:bg-red-500/80"
        >
          <X size={20} aria-hidden />
        </button>
      </div>
    </>
  );
}

function Centered({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8">
      {children}
      {label && <p className="text-sm text-second">{label}</p>}
    </div>
  );
}
