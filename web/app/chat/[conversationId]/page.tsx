import { redirect } from "next/navigation";

import { auth } from "@/auth";
import { ChatPageClient } from "@/components/chat-page-client";

function googleSignInConfigured(): boolean {
  return Boolean(
    process.env.AUTH_SECRET?.trim() &&
      process.env.AUTH_GOOGLE_ID?.trim() &&
      process.env.AUTH_GOOGLE_SECRET?.trim() &&
      process.env.AGENT_OPS_TOKEN?.trim(),
  );
}

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

  return <ChatPageClient conversationId={conversationId} googleConfigured={googleSignInConfigured()} />;
}
