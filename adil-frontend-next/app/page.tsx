import { redirect } from "next/navigation";
import { randomUUID } from "crypto";

export default function HomePage() {
  const id = randomUUID();
  redirect(`/chat/${id}`);
}
