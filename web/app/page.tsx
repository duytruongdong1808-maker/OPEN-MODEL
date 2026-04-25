import { redirect } from "next/navigation";

import { auth } from "@/auth";
import { HomeBootstrap } from "@/components/home-bootstrap";

export default async function HomePage() {
  const session = await auth();
  if (!session?.user) {
    redirect("/login?callbackUrl=/");
  }

  return <HomeBootstrap />;
}
