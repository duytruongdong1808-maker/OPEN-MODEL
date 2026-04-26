"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ChatShell } from "@/components/chat-shell";
import { createBrowserApiClient } from "@/lib/api";

export function ChatPageClient({
  conversationId,
  googleConfigured,
}: {
  conversationId: string;
  googleConfigured: boolean;
}) {
  const router = useRouter();
  const [apiClient] = useState(() => createBrowserApiClient());

  return (
    <ChatShell
      apiClient={apiClient}
      conversationId={conversationId}
      googleConfigured={googleConfigured}
      onNavigateConversation={(nextConversationId) => router.push(`/chat/${nextConversationId}`)}
    />
  );
}
