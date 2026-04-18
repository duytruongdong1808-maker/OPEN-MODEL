"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";

import { ChatShell } from "@/components/chat-shell";
import { createBrowserApiClient } from "@/lib/api";

export default function ChatPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = use(params);
  const router = useRouter();
  const [apiClient] = useState(() => createBrowserApiClient());

  return (
    <ChatShell
      apiClient={apiClient}
      conversationId={conversationId}
      onNavigateConversation={(conversationId) => router.push(`/chat/${conversationId}`)}
    />
  );
}
