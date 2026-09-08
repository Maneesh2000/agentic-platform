import { ChatShell } from "@/components/ChatShell";
import { auth } from "@/lib/auth";

export default async function Page() {
  const session = await auth(); // middleware guarantees a session here
  const user = {
    name: session?.user?.name ?? "You",
    email: session?.user?.email ?? "",
  };

  return <ChatShell user={user} />;
}
