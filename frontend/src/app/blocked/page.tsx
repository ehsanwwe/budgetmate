import { redirect } from "next/navigation";

export default function BlockedRedirect() {
  redirect("/fa/blocked");
}
