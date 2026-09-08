// Text-chat proxy. The browser never talks to the Python service directly —
// same rule as /api/token with LiveKit credentials: the service address and
// the user's identity stay server-side.
//
// This route owns conversation state; the Python service is stateless and is
// handed the full message list each turn.
import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { appendMessage, getMessages } from "@/lib/chatDb";

export const runtime = "nodejs"; // pg + streaming; never Edge
export const dynamic = "force-dynamic";

const CHAT_SERVICE_URL = process.env.CHAT_SERVICE_URL ?? "http://localhost:8124";

export async function POST(req: NextRequest) {
  // JSON 401, not the middleware's HTML redirect — a redirect body would be
  // parsed as an event stream and fail confusingly in the client.
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }
  const userId = session.user.id;

  const { conversationId, message, attachments } = await req.json();
  if (typeof conversationId !== "string" || typeof message !== "string" || !message.trim()) {
    return NextResponse.json({ error: "conversationId and message are required" }, { status: 422 });
  }

  const history = await getMessages(userId, conversationId);
  if (history === null) {
    // Not found rather than forbidden: don't confirm another user's ids exist.
    return NextResponse.json({ error: "Conversation not found" }, { status: 404 });
  }

  await appendMessage(userId, conversationId, { role: "user", content: message });

  let upstream: Response;
  try {
    upstream = await fetch(`${CHAT_SERVICE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [...history, { role: "user", content: message }],
        // The assistant is stateless: identity and attachments travel with
        // the turn. user_id is for the audit trail only, never authorization.
        user_id: userId,
        attachments: Array.isArray(attachments) ? attachments : [],
      }),
    });
  } catch {
    return NextResponse.json({ error: "The assistant is unavailable." }, { status: 502 });
  }
  if (!upstream.ok || !upstream.body) {
    return NextResponse.json({ error: "The assistant is unavailable." }, { status: 502 });
  }

  // Tee the stream: forward every byte to the browser as it arrives, while
  // accumulating token text so the finished reply can be persisted. Buffering
  // the whole reply first would throw away the streaming that makes this feel
  // responsive.
  const decoder = new TextDecoder();
  let assistant = "";
  let carry = "";

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const reader = upstream.body!.getReader();
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          controller.enqueue(value);

          carry += decoder.decode(value, { stream: true });
          const lines = carry.split("\n");
          carry = lines.pop() ?? ""; // keep the partial line for the next chunk
          let event = "";
          for (const line of lines) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:") && event === "token") {
              try {
                assistant += JSON.parse(line.slice(5)).text ?? "";
              } catch {
                /* a split frame; the next chunk completes it */
              }
            }
          }
        }
      } finally {
        controller.close();
        if (assistant.trim()) {
          await appendMessage(userId, conversationId, {
            role: "assistant",
            content: assistant,
          });
        }
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no", // don't let a proxy buffer the stream
    },
  });
}
