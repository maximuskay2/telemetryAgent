import { redirect } from "next/navigation";

// S10: /mission moved home. Kept as a redirect for bookmarks and links.
export default function MissionRedirect() {
  redirect("/");
}
