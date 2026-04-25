import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

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

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  pages: {
    signIn: "/login",
  },
  session: {
    strategy: "jwt",
  },
  providers: [
    Credentials({
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const expected = configuredCredentials();
        const username = typeof credentials?.username === "string" ? credentials.username : "";
        const password = typeof credentials?.password === "string" ? credentials.password : "";
        if (!expected) return null;
        if (
          !secureCompare(username, expected.username) ||
          !secureCompare(password, expected.password)
        ) {
          return null;
        }
        return {
          id: "local-user",
          name: expected.username,
        };
      },
    }),
  ],
});
