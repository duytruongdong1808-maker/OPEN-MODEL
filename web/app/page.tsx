"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { createBrowserApiClient, formatApiError } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrapConversation() {
      const apiClient = createBrowserApiClient();
      try {
        const conversations = await apiClient.listConversations();
        if (cancelled) {
          return;
        }
        if (conversations.length > 0) {
          router.replace(`/chat/${conversations[0].id}`);
          return;
        }
        const conversation = await apiClient.createConversation();
        if (!cancelled) {
          router.replace(`/chat/${conversation.id}`);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(formatApiError(cause));
        }
      }
    }

    void bootstrapConversation();

    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-6 sm:px-6">
      <section className="app-surface w-full max-w-2xl rounded-[24px] px-6 py-8 sm:px-8 sm:py-10">
        <div className="flex items-center gap-3">
          <span className="h-2.5 w-2.5 rounded-full bg-action" aria-hidden="true" />
          <p className="app-meta text-content-secondary">Open Model</p>
        </div>

        <h1 className="mt-6 max-w-xl text-3xl font-semibold tracking-tight text-content-primary sm:text-4xl">
          Preparing your workspace
        </h1>

        <p className="mt-3 max-w-xl text-sm leading-6 text-content-secondary sm:text-base">
          {error ?? "Loading the latest conversation or creating a fresh thread."}
        </p>

        <div className="mt-8 grid gap-3 border-t border-stroke-subtle pt-5 text-sm text-content-secondary sm:grid-cols-2">
          <div className="rounded-[16px] border border-stroke-subtle bg-surface-strong px-4 py-4">
            <p className="app-meta text-content-secondary">State</p>
            <p className="mt-2 font-medium text-content-primary">{error ? "Startup issue" : "Bootstrapping"}</p>
          </div>
          <div className="rounded-[16px] border border-stroke-subtle bg-surface-strong px-4 py-4">
            <p className="app-meta text-content-secondary">Flow</p>
            <p className="mt-2 font-medium text-content-primary">Restore thread or open a new session</p>
          </div>
        </div>
      </section>
    </main>
  );
}
