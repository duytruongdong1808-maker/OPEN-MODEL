"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { IconMail } from "@/components/ui/icons";

export function HomeBootstrap() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrapConversation() {
      try {
        await Promise.resolve();
        if (cancelled) return;
        router.replace("/mail");
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Unable to open mail.");
      }
    }

    void bootstrapConversation();

    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-10">
      <section className="w-full max-w-md rounded-xl border border-line bg-bg-rail px-6 py-8 shadow-soft">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-[9px] border border-accent-ring bg-accent-soft text-accent-fg">
            <IconMail size={15} />
          </span>
          <div>
            <div className="text-[13.5px] font-semibold tracking-tight text-text">Mail Agent</div>
            <div className="om-meta">Gmail - read-only</div>
          </div>
        </div>

        <h1 className="mt-6 text-2xl font-semibold tracking-tight text-text">
          {error ? "Couldn't open mail" : "Opening mail workspace"}
        </h1>

        <p className="mt-2 text-sm leading-6 text-text-3">
          {error ?? "Loading the Gmail triage dashboard..."}
        </p>

        {!error && (
          <div className="mt-6 flex items-center gap-1.5 font-mono text-[10.5px] text-text-3">
            <span className="h-1 w-1 animate-om-pulse rounded-full bg-accent-fg" />
            <span className="h-1 w-1 animate-om-pulse rounded-full bg-accent-fg [animation-delay:.15s]" />
            <span className="h-1 w-1 animate-om-pulse rounded-full bg-accent-fg [animation-delay:.3s]" />
            Connecting
          </div>
        )}
      </section>
    </main>
  );
}
