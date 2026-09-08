"use client";

import { useEffect, useState } from "react";
import { Palette, Settings, ShieldCheck, Trash2, User, X } from "lucide-react";
import { toast } from "sonner";

type Section = "general" | "account" | "data";

/**
 * Settings, honestly scoped: only controls that do something are enabled.
 * The categories mirror the familiar layout without pretending we have
 * notification preferences or billing.
 */
export function SettingsModal({
  user,
  onClose,
}: {
  user: { name: string; email: string };
  onClose: () => void;
}) {
  const [section, setSection] = useState<Section>("general");
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const deleteAll = async () => {
    setDeleting(true);
    try {
      const res = await fetch("/api/conversations", { method: "DELETE" });
      if (!res.ok) throw new Error("Could not delete chats");
      toast.success("All chats deleted");
      window.location.reload(); // simplest correct refresh of every list
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not delete chats");
      setDeleting(false);
    }
  };

  const items: { id: Section; label: string; icon: typeof Settings }[] = [
    { id: "general", label: "General", icon: Settings },
    { id: "account", label: "Account", icon: User },
    { id: "data", label: "Data controls", icon: ShieldCheck },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex h-[480px] w-full max-w-2xl overflow-hidden rounded-2xl border border-edge bg-elevated shadow-2xl"
      >
        {/* left rail */}
        <div className="w-48 shrink-0 border-r border-edge p-3">
          <button
            onClick={onClose}
            aria-label="Close settings"
            className="mb-3 rounded-lg p-2 text-second transition hover:bg-hover hover:text-body"
          >
            <X size={16} aria-hidden />
          </button>
          {items.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setSection(id)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${
                section === id ? "bg-active" : "hover:bg-hover"
              }`}
            >
              <Icon size={15} aria-hidden className="text-second" />
              {label}
            </button>
          ))}
        </div>

        {/* pane */}
        <div className="flex-1 overflow-y-auto p-6">
          {section === "general" && (
            <>
              <h2 className="mb-4 text-lg font-semibold">General</h2>
              <Row label="Appearance" value="Dark" icon={Palette} />
              <Row label="Language" value="Auto-detect" />
              <Row label="Voice provider" value="Deepgram (STT + TTS)" />
              <Row label="Model" value="Configured by the server (LLM_MODEL)" />
            </>
          )}

          {section === "account" && (
            <>
              <h2 className="mb-4 text-lg font-semibold">Account</h2>
              <Row label="Name" value={user.name} />
              <Row label="Email" value={user.email} />
              <Row label="Plan" value="Self-hosted" />
            </>
          )}

          {section === "data" && (
            <>
              <h2 className="mb-4 text-lg font-semibold">Data controls</h2>
              <p className="mb-4 text-sm text-second">
                Chats and uploads are stored in your own Postgres. Voice
                conversations are never stored.
              </p>
              <div className="flex items-center justify-between border-t border-edge py-4">
                <span className="text-sm">Delete all chats</span>
                {confirming ? (
                  <span className="flex items-center gap-2">
                    <button
                      onClick={deleteAll}
                      disabled={deleting}
                      className="rounded-full bg-red-600 px-4 py-1.5 text-sm font-medium transition hover:bg-red-500 disabled:opacity-50"
                    >
                      {deleting ? "Deleting…" : "Confirm delete"}
                    </button>
                    <button
                      onClick={() => setConfirming(false)}
                      className="rounded-full px-3 py-1.5 text-sm text-second hover:text-body"
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    onClick={() => setConfirming(true)}
                    className="flex items-center gap-1.5 rounded-full border border-red-500/40 px-4 py-1.5 text-sm text-red-400 transition hover:bg-red-500/10"
                  >
                    <Trash2 size={14} aria-hidden />
                    Delete all
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon?: typeof Settings;
}) {
  return (
    <div className="flex items-center justify-between border-t border-edge py-4 first-of-type:border-t-0">
      <span className="flex items-center gap-2.5 text-sm">
        {Icon && <Icon size={15} aria-hidden className="text-second" />}
        {label}
      </span>
      <span className="text-sm text-second">{value}</span>
    </div>
  );
}
