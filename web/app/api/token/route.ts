// Access-token minting. MUST run on the Node runtime — livekit-server-sdk
// token signing does not work on Edge, so there is deliberately no
// `export const runtime = "edge"` here (the old app's routes all had one).
import { NextResponse } from "next/server";
import { AccessToken } from "livekit-server-sdk";
import { RoomAgentDispatch, RoomConfiguration } from "@livekit/protocol";
import { auth } from "@/lib/auth";

export const dynamic = "force-dynamic"; // a token is never cacheable

export async function GET() {
  // Room tokens are only minted for signed-in users; the LiveKit identity
  // IS the app user id, so the worker and downstream ACLs see a real user.
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }

  const { LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET } = process.env;
  if (!LIVEKIT_URL || !LIVEKIT_API_KEY || !LIVEKIT_API_SECRET) {
    return NextResponse.json(
      { error: "LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET are not configured" },
      { status: 500 },
    );
  }

  const suffix = crypto.randomUUID().slice(0, 8);
  const roomName = `voice-${suffix}`;

  const at = new AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, {
    identity: session.user.id,
    name: session.user.name ?? session.user.email ?? undefined,
    ttl: "15m",
  });
  at.addGrant({
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
  });

  // The worker uses explicit dispatch (it registered with an agent_name),
  // so the token must REQUEST the agent — without this block the room
  // opens and no agent ever joins (gotcha 2).
  const agentName = process.env.LIVEKIT_AGENT_NAME ?? "chat-assistant";
  if (agentName) {
    at.roomConfig = new RoomConfiguration({
      agents: [new RoomAgentDispatch({ agentName })],
    });
  }

  return NextResponse.json({ serverUrl: LIVEKIT_URL, token: await at.toJwt() });
}
