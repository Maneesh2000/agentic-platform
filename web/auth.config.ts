// Edge-safe Auth.js config shared by middleware and the full server config.
// MUST stay free of Node-only imports (pg, bcrypt) — middleware runs on the
// Edge runtime and only needs to verify the JWT cookie.
import type { NextAuthConfig } from "next-auth";

export const authConfig = {
  // Self-hosted (no fixed AUTH_URL): derive the callback host from the
  // request. Required by Auth.js v5 outside Vercel.
  trustHost: true,
  session: { strategy: "jwt" },
  pages: { signIn: "/signin" },
  providers: [], // real providers live in lib/auth.ts (Node runtime only)
  callbacks: {
    authorized({ auth, request }) {
      const loggedIn = !!auth?.user;
      const { pathname } = request.nextUrl;
      const onAuthPage =
        pathname.startsWith("/signin") || pathname.startsWith("/signup");
      if (onAuthPage) {
        return loggedIn ? Response.redirect(new URL("/", request.nextUrl)) : true;
      }
      return loggedIn; // false → redirect to pages.signIn
    },
    jwt({ token, user }) {
      if (user) token.id = user.id;
      return token;
    },
    session({ session, token }) {
      if (session.user && typeof token.id === "string") {
        session.user.id = token.id;
      }
      return session;
    },
  },
} satisfies NextAuthConfig;
