import { LoginForm } from "@/app/login/login-form";

function googleSignInConfigured(): boolean {
  return Boolean(
    process.env.AUTH_SECRET?.trim() &&
      process.env.AUTH_GOOGLE_ID?.trim() &&
      process.env.AUTH_GOOGLE_SECRET?.trim() &&
      process.env.AGENT_OPS_TOKEN?.trim(),
  );
}

export default function LoginPage() {
  return <LoginForm googleConfigured={googleSignInConfigured()} />;
}

