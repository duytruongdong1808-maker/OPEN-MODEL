"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ChatShell } from "@/components/chat-shell";
import { createBrowserApiClient } from "@/lib/api";

export function ChatPageClient({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const [apiClient] = useState(() => createBrowserApiClient());

  return (
    <ChatShell
      apiClient={apiClient}
      conversationId={conversationId}
      onNavigateConversation={(nextConversationId) => router.push(`/chat/${nextConversationId}`)}
    />
  );
}
