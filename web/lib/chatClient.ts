// SSE parsing for the text surface.
//
// Hand-rolled rather than EventSource because EventSource cannot POST, and
// the request carries the conversation id and message. Payloads are JSON
// objects, not raw text: a token may be a single space or contain newlines
// (markdown replies are full of both), neither of which survives raw SSE
// data lines intact.

export type ChatEvent =
  | { type: "token"; text: string }
  | { type: "status"; text: string }
  | { type: "error"; text: string };

export interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

export interface Attachment {
  id: string;
  filename: string;
}

export async function uploadFile(file: File): Promise<Attachment> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/uploads", { method: "POST", body: form });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error ?? "Upload failed");
  return { id: body.id, filename: body.filename };
}

export async function* streamChat(
  conversationId: string,
  message: string,
  attachments: Attachment[] = [],
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversationId, message, attachments }),
    signal,
  });

  if (!res.ok || !res.body) {
    const detail = await res.json().catch(() => null);
    yield { type: "error", text: detail?.error ?? "The assistant is unavailable." };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let carry = "";
  let event = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    carry += decoder.decode(value, { stream: true });

    const lines = carry.split("\n");
    carry = lines.pop() ?? ""; // a partial line finishes in the next chunk

    for (const line of lines) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        if (event === "done" || !event) continue;
        let text = "";
        try {
          text = JSON.parse(line.slice(5)).text ?? "";
        } catch {
          continue;
        }
        if (event === "token" || event === "status" || event === "error") {
          yield { type: event, text };
        }
      }
    }
  }
}

export async function listConversations(): Promise<Conversation[]> {
  const res = await fetch("/api/conversations");
  if (!res.ok) return [];
  return (await res.json()).conversations ?? [];
}

export async function createConversation(): Promise<Conversation | null> {
  const res = await fetch("/api/conversations", { method: "POST" });
  return res.ok ? await res.json() : null;
}

export async function deleteConversation(id: string): Promise<void> {
  await fetch(`/api/conversations/${id}`, { method: "DELETE" });
}

export async function fetchMessages(
  id: string,
): Promise<{ role: "user" | "assistant"; content: string }[]> {
  const res = await fetch(`/api/conversations/${id}`);
  if (!res.ok) return [];
  return (await res.json()).messages ?? [];
}
