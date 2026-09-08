// Session gate for every PAGE except the auth screens and static assets.
// Uses the edge-safe config (no pg/bcrypt imports) — the authorized()
// callback in auth.config.ts decides redirects.
//
// API routes are excluded on purpose. The middleware's response to an
// unauthenticated request is a 307 redirect to /signin, which is right for a
// page and wrong for fetch(): an SSE reader would try to parse the sign-in
// HTML as an event stream. Every route under app/api therefore performs its
// own `auth()` check and returns a JSON 401 (see api/chat, api/conversations,
// api/token) — which a client can actually act on.
import NextAuth from "next-auth";
import { authConfig } from "@/auth.config";

export const middleware = NextAuth(authConfig).auth;

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
