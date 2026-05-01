import { redirect } from "next/navigation";

import { auth } from "@/auth";
import { MailDashboard } from "@/features/mail/MailDashboard";

function googleSignInConfigured(): boolean {
  return Boolean(
    process.env.AUTH_SECRET?.trim() &&
      process.env.AUTH_GOOGLE_ID?.trim() &&
      process.env.AUTH_GOOGLE_SECRET?.trim() &&
      process.env.AGENT_OPS_TOKEN?.trim(),
  );
}

export default async function MailPage() {
  const session = await auth();
  if (!session?.user) {
    redirect(`/login?callbackUrl=${encodeURIComponent("/mail")}`);
  }

  return <MailDashboard googleConfigured={googleSignInConfigured()} />;
}
