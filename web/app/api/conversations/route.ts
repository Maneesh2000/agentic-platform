import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import {
  createConversation,
  deleteAllConversations,
  listConversations,
} from "@/lib/chatDb";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }
  return NextResponse.json({ conversations: await listConversations(session.user.id) });
}

export async function POST() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }
  return NextResponse.json(await createConversation(session.user.id), { status: 201 });
}

// Settings > Data controls > "Delete all chats".
export async function DELETE() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }
  const deleted = await deleteAllConversations(session.user.id);
  return NextResponse.json({ deleted });
}
