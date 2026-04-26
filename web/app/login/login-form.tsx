"use client";

import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { signIn } from "next-auth/react";

import { IconModel } from "@/components/icons";

type LoginFormProps = {
  googleConfigured: boolean;
};

function LoginFormContent({ googleConfigured }: LoginFormProps) {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") || "/";
  const oauthError = searchParams.get("error");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(
    oauthError ? "Unable to sign in with Google." : null,
  );
  const [pending, setPending] = useState(false);
  const [googlePending, setGooglePending] = useState(false);

  async function onGoogleSignIn() {
    if (!googleConfigured) {
      setError("Google sign-in is not configured on this server.");
      return;
    }
    setGooglePending(true);
    setError(null);
    await signIn("google", { callbackUrl });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const result = await signIn("credentials", {
      username,
      password,
      callbackUrl,
      redirect: false,
    });
    setPending(false);
    if (result?.error) {
      setError("Invalid username or password.");
      return;
    }
    window.location.assign(result?.url || callbackUrl);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-bg-thread px-6 py-10">
      <section className="w-full max-w-sm rounded-xl border border-line bg-bg-rail px-6 py-7 shadow-soft">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-[9px] border border-accent-ring bg-accent-soft text-accent-fg">
            <IconModel size={15} />
          </span>
          <div>
            <div className="text-[13.5px] font-semibold tracking-tight text-text">Open Model</div>
            <div className="om-meta">Local workspace</div>
          </div>
        </div>

        <h1 className="mt-6 text-xl font-semibold tracking-tight text-text">Sign in</h1>

        <button
          type="button"
          disabled={googlePending || pending}
          onClick={onGoogleSignIn}
          className="om-btn mt-5 w-full justify-center py-2"
        >
          {googlePending ? "Connecting..." : "Continue with Google"}
        </button>

        <div className="my-4 flex items-center gap-3">
          <span className="h-px flex-1 bg-line" />
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-4">
            or
          </span>
          <span className="h-px flex-1 bg-line" />
        </div>

        <form className="flex flex-col gap-3" onSubmit={onSubmit}>
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-text-2">Username</span>
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="om-focus rounded-md border border-line bg-bg-input px-3 py-2 text-[13px] text-text outline-none"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-text-2">Password</span>
            <input
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="om-focus rounded-md border border-line bg-bg-input px-3 py-2 text-[13px] text-text outline-none"
            />
          </label>
          {error ? (
            <div
              role="alert"
              className="rounded-md border border-err-bd bg-err-bg px-3 py-2 text-[12px] text-err-fg"
            >
              {error}
            </div>
          ) : null}
          <button type="submit" disabled={pending || googlePending} className="om-btn om-btn-primary mt-1 justify-center">
            {pending ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

export function LoginForm(props: LoginFormProps) {
  return (
    <Suspense>
      <LoginFormContent {...props} />
    </Suspense>
  );
}

