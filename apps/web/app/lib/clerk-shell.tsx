// Clerk provider shell (C-N7). Client-only: importing @clerk/nextjs
// in the server-component layout crashes prerendering, so the
// provider lives here and the layout stays a plain wrapper.
"use client";

import { ClerkProvider } from "@clerk/nextjs";
import type { ReactNode } from "react";
import { clerkPublishableKey } from "./session";

export default function ClerkShell({ children }: { children: ReactNode }) {
  if (clerkPublishableKey === "") return <>{children}</>;
  return (
    <ClerkProvider publishableKey={clerkPublishableKey}>
      {children}
    </ClerkProvider>
  );
}
