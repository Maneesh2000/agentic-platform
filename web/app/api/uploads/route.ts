// File upload for chat attachments. Bytes go into Postgres (app_uploads) so
// the Python assistant can read them by id without sharing a filesystem with
// this container — see lib/chatDb.ts for why.
import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { saveUpload } from "@/lib/chatDb";

export const runtime = "nodejs"; // pg + Buffer; never Edge
export const dynamic = "force-dynamic";

const MAX_BYTES = 10 * 1024 * 1024; // keep in step with MAX_DOCUMENT_BYTES
const ALLOWED = [".txt", ".md", ".pdf", ".html", ".htm"];

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }

  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file supplied" }, { status: 422 });
  }

  const dot = file.name.lastIndexOf(".");
  const suffix = dot === -1 ? "" : file.name.slice(dot).toLowerCase();
  if (!ALLOWED.includes(suffix)) {
    return NextResponse.json(
      { error: `Unsupported file type ${suffix || "(none)"}. Try ${ALLOWED.join(", ")}.` },
      { status: 415 },
    );
  }
  // Refuse on the declared size before buffering the body into memory.
  if (file.size > MAX_BYTES) {
    return NextResponse.json({ error: "File is larger than 10MB" }, { status: 413 });
  }

  const content = Buffer.from(await file.arrayBuffer());
  if (content.byteLength > MAX_BYTES) {
    return NextResponse.json({ error: "File is larger than 10MB" }, { status: 413 });
  }

  const upload = await saveUpload(
    session.user.id,
    file.name,
    file.type || "application/octet-stream",
    content,
  );
  return NextResponse.json(upload, { status: 201 });
}
