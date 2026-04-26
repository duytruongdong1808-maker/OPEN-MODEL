import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";

const GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly";
const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

type GoogleProfile = {
  sub?: string;
  email?: string;
};

type SessionWithGoogle = {
  googleUserId?: string;
  googleEmail?: string;
  authProvider?: string;
  user?: {
    id?: string;
    name?: string | null;
    email?: string | null;
    image?: string | null;
  };
};

type TokenWithGoogle = {
  googleUserId?: string;
  googleEmail?: string;
  authProvider?: string;
};

function googleProviderConfigured(): boolean {
  return Boolean(process.env.AUTH_GOOGLE_ID?.trim() && process.env.AUTH_GOOGLE_SECRET?.trim());
}

function secureCompare(left: string, right: string): boolean {
  const maxLength = Math.max(left.length, right.length);
  let mismatch = left.length ^ right.length;
  for (let index = 0; index < maxLength; index += 1) {
    mismatch |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return mismatch === 0;
}

function configuredCredentials(): { username: string; password: string } | null {
  const username = process.env.AUTH_USERNAME?.trim();
  const password = process.env.AUTH_PASSWORD ?? "";
  if (!username || !password) return null;
  return { username, password };
}

function resolveBackendUrl(): string {
  return (process.env.OPEN_MODEL_API_BASE_URL?.trim() || DEFAULT_BACKEND_URL).replace(/\/$/, "");
}

function resolveOpsToken(): string | null {
  return process.env.AGENT_OPS_TOKEN?.trim() || null;
}

async function auditLogin({
  userId,
  result,
  provider,
  reason,
}: {
  userId: string;
  result: "success" | "denied" | "error";
  provider: string;
  reason?: string;
}): Promise<void> {
  const opsToken = resolveOpsToken();
  if (!opsToken) return;

  try {
    await fetch(`${resolveBackendUrl()}/audit/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${opsToken}`,
      },
      body: JSON.stringify({
        user_id: userId || "unknown",
        result,
        provider,
        reason,
      }),
    });
  } catch {
    // Login audit is best-effort; authentication must not depend on audit availability.
  }
}

async function syncGoogleTokenToBackend({
  userId,
  email,
  accessToken,
  refreshToken,
  expiresAt,
  scope,
  tokenType,
}: {
  userId: string;
  email?: string | null;
  accessToken?: string;
  refreshToken?: string;
  expiresAt?: number;
  scope?: string;
  tokenType?: string;
}): Promise<boolean> {
  const opsToken = resolveOpsToken();
  const clientId = process.env.AUTH_GOOGLE_ID?.trim();
  const clientSecret = process.env.AUTH_GOOGLE_SECRET?.trim();
  if (!opsToken || !clientId || !clientSecret || !accessToken) {
    return false;
  }

  try {
    const response = await fetch(`${resolveBackendUrl()}/auth/gmail/session-token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${opsToken}`,
      },
      body: JSON.stringify({
        user_id: userId,
        email,
        access_token: accessToken,
        refresh_token: refreshToken,
        expires_at: expiresAt,
        scope,
        token_type: tokenType,
        client_id: clientId,
        client_secret: clientSecret,
      }),
    });

    return response.ok;
  } catch {
    return false;
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  pages: {
    signIn: "/login",
  },
  session: {
    strategy: "jwt",
  },
  callbacks: {
    async signIn({ account, profile }) {
      if (account?.provider !== "google") return true;
      const googleProfile = profile as GoogleProfile | undefined;
      const userId = account.providerAccountId || googleProfile?.sub;
      if (!userId) {
        await auditLogin({
          userId: "unknown",
          result: "denied",
          provider: "google",
          reason: "missing_google_user_id",
        });
        return false;
      }
      const synced = await syncGoogleTokenToBackend({
        userId,
        email: googleProfile?.email,
        accessToken: account.access_token,
        refreshToken: account.refresh_token,
        expiresAt: account.expires_at,
        scope: account.scope,
        tokenType: account.token_type,
      });
      await auditLogin({
        userId,
        result: synced ? "success" : "error",
        provider: "google",
        reason: synced ? undefined : "gmail_token_sync_failed",
      });
      return synced ? true : "/login?error=GmailTokenSync";
    },
    async jwt({ token, account, profile }) {
      const nextToken = token as typeof token & TokenWithGoogle;
      if (account?.provider === "google") {
        const googleProfile = profile as GoogleProfile | undefined;
        nextToken.googleUserId = account.providerAccountId || googleProfile?.sub;
        nextToken.googleEmail = googleProfile?.email ?? token.email ?? undefined;
        nextToken.authProvider = "google";
      } else if (account?.provider === "credentials") {
        nextToken.googleUserId = undefined;
        nextToken.googleEmail = undefined;
        nextToken.authProvider = "credentials";
      }
      return nextToken;
    },
    async session({ session, token }) {
      const sourceToken = token as typeof token & TokenWithGoogle;
      const nextSession = session as typeof session & SessionWithGoogle;
      if (nextSession.user && sourceToken.sub) {
        nextSession.user.id = sourceToken.sub;
      }
      nextSession.googleUserId = sourceToken.googleUserId;
      nextSession.googleEmail = sourceToken.googleEmail;
      nextSession.authProvider = sourceToken.authProvider;
      return nextSession;
    },
  },
  providers: [
    ...(googleProviderConfigured()
      ? [
          Google({
            clientId: process.env.AUTH_GOOGLE_ID?.trim(),
            clientSecret: process.env.AUTH_GOOGLE_SECRET?.trim(),
            authorization: {
              params: {
                scope: `openid email profile ${GMAIL_READONLY_SCOPE}`,
                access_type: "offline",
                prompt: "consent",
                response_type: "code",
              },
            },
          }),
        ]
      : []),
    Credentials({
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const expected = configuredCredentials();
        const username = typeof credentials?.username === "string" ? credentials.username : "";
        const password = typeof credentials?.password === "string" ? credentials.password : "";
        if (!expected) {
          await auditLogin({
            userId: username || "unknown",
            result: "error",
            provider: "credentials",
            reason: "credentials_not_configured",
          });
          return null;
        }
        if (
          !secureCompare(username, expected.username) ||
          !secureCompare(password, expected.password)
        ) {
          await auditLogin({
            userId: username || "unknown",
            result: "denied",
            provider: "credentials",
            reason: "invalid_credentials",
          });
          return null;
        }
        await auditLogin({
          userId: "local-user",
          result: "success",
          provider: "credentials",
        });
        return {
          id: "local-user",
          name: expected.username,
        };
      },
    }),
  ],
});
