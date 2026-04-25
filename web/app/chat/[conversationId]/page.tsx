import { redirect } from "next/navigation";

import { auth } from "@/auth";
import { ChatPageClient } from "@/components/chat-page-client";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;
  const session = await auth();
  if (!session?.user) {
    redirect(`/login?callbackUrl=${encodeURIComponent(`/chat/${conversationId}`)}`);
  }

  return <ChatPageClient conversationId={conversationId} />;
}
