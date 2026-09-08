"use client";

import { useEffect, useRef, useState } from "react";
import { signOut } from "next-auth/react";
import { LogOut, Settings } from "lucide-react";
import { SettingsModal } from "@/components/SettingsModal";

export function AccountMenu({ user }: { user: { name: string; email: string } }) {
  const [open, setOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape — a popover that traps you is worse
  // than no popover.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const initials = (user.name || user.email)
    .split(/[\s@.]+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div ref={ref} className="relative border-t border-edge p-2">
      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-2 right-2 mb-2 overflow-hidden rounded-2xl border border-edge bg-elevated shadow-2xl"
        >
          <div className="border-b border-edge px-4 py-3">
            <p className="truncate text-sm font-medium">{user.name}</p>
            <p className="truncate text-xs text-muted">{user.email}</p>
          </div>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              setSettingsOpen(true);
            }}
            className="flex w-full items-center gap-3 px-4 py-2.5 text-sm transition hover:bg-hover"
          >
            <Settings size={16} aria-hidden className="text-second" />
            Settings
          </button>
          <button
            role="menuitem"
            onClick={() => signOut({ callbackUrl: "/signin" })}
            className="flex w-full items-center gap-3 px-4 py-2.5 text-sm transition hover:bg-hover"
          >
            <LogOut size={16} aria-hidden className="text-second" />
            Log out
          </button>
        </div>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex w-full items-center gap-3 rounded-lg px-2 py-2 transition hover:bg-hover"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-fuchsia-600 text-xs font-semibold">
          {initials}
        </span>
        <span className="min-w-0 flex-1 text-left">
          <span className="block truncate text-sm">{user.name}</span>
          <span className="block truncate text-xs text-muted">Self-hosted</span>
        </span>
      </button>

      {settingsOpen && <SettingsModal user={user} onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
