"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { createBrowserApiClient } from "@/lib/api";

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
          setError(cause instanceof Error ? cause.message : "Unable to connect to the chat API.");
        }
      }
    }

    void bootstrapConversation();

    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="max-w-md rounded-[2rem] border border-black/5 bg-white/80 p-8 text-center shadow-shell backdrop-blur">
        <p className="font-mono text-xs uppercase tracking-[0.35em] text-accent-700">Open Model</p>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-shell-900">
          Preparing your workspace
        </h1>
        <p className="mt-3 text-sm leading-6 text-shell-700">
          {error ?? "Loading the latest conversation or creating a fresh thread for you."}
        </p>
      </div>
    </main>
  );
}
