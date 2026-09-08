import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { deleteConversation, getMessages } from "@/lib/chatDb";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }
  const { id } = await params;
  const messages = await getMessages(session.user.id, id);
  // 404 rather than 403: another user's conversation id is not confirmed.
  if (messages === null) {
    return NextResponse.json({ error: "Conversation not found" }, { status: 404 });
  }
  return NextResponse.json({ messages });
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }
  const { id } = await params;
  if (!(await deleteConversation(session.user.id, id))) {
    return NextResponse.json({ error: "Conversation not found" }, { status: 404 });
  }
  return new NextResponse(null, { status: 204 });
}
