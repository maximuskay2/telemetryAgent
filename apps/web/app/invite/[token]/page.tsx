// Invite accept (C-N3): join an org from an invite link.
"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import ThemeToggle from "../../components/ThemeToggle";
import { useSession } from "../../lib/session";
import { Card } from "../../ui";
import { ApiErrorView, Loading } from "../../commerce/components";

export default function InvitePage() {
  const params = useParams<{ token: string }>();
  const { status, api } = useSession();
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<{ org_id: string; role: string } | null>(
    null,
  );
  const token = params?.token ?? "";

  if (status === "loading") {
    return (
      <main className="mx-auto w-full max-w-md px-4 py-8">
        <Loading />
      </main>
    );
  }
  if (status === "signed-out") {
    return (
      <main className="mx-auto w-full max-w-md space-y-4 px-4 py-8">
        <p className="text-sm text-text-muted">
          Sign in to accept this invite.{" "}
          <Link href="/signin" className="text-brand-cyan">
            Sign in
          </Link>
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-md space-y-4 px-4 py-8">
      <div className="flex items-start justify-between gap-3">
        <h1 className="mb-1 text-xl font-semibold text-text">
          Join organization
        </h1>
        <ThemeToggle />
      </div>
      {error ? (
        <ApiErrorView error={error} />
      ) : done ? (
        <Card title="You're in">
          <p className="text-sm text-text-muted">
            Joined as {done.role}.{" "}
            <button
              type="button"
              onClick={() => router.push("/")}
              className="cursor-pointer text-brand-cyan outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              Open Mission Control
            </button>
          </p>
        </Card>
      ) : (
        <Card title="Team invite">
          <p className="mb-3 text-sm text-text-muted">
            Accept to join with the invited role.
          </p>
          <button
            type="button"
            onClick={() => {
              setError(null);
              api
                .acceptInvite(token)
                .then((out) => setDone(out))
                .catch((err: unknown) => setError(err));
            }}
            className="cursor-pointer rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
          >
            Accept invite
          </button>
        </Card>
      )}
    </main>
  );
}
