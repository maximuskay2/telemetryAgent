// Members (C-N3): list, invite, remove, transfer, delete org.
"use client";

import { useCallback, useEffect, useState } from "react";
import { Member } from "../lib/commerce";
import { useSession } from "../lib/session";
import { Card } from "../ui";
import AccountChrome from "../commerce/AccountChrome";
import RequireAuth from "../commerce/RequireAuth";
import {
  ApiErrorView,
  InviteForm,
  Loading,
  MemberList,
} from "../commerce/components";

export default function MembersPage() {
  return (
    <RequireAuth>
      <AccountChrome>
        <MembersInner />
      </AccountChrome>
    </RequireAuth>
  );
}

function MembersInner() {
  const { user, activeOrg, role, api } = useSession();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");

  const reload = useCallback(async () => {
    if (!activeOrg) return;
    setError(null);
    try {
      const out = await api.listMembers(activeOrg.id);
      setMembers(out.members);
    } catch (err) {
      setError(err);
    }
  }, [api, activeOrg]);

  useEffect(() => {
    setMembers(null);
    void reload();
  }, [reload]);

  if (!activeOrg) {
    return (
      <main className="mx-auto w-full max-w-2xl px-4 py-8">
        <p className="text-sm text-text-muted">Creating your organization…</p>
      </main>
    );
  }

  const canManage = role === "owner" || role === "admin";
  const isOwner = role === "owner";

  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 px-4 py-8">
      <div>
        <h1 className="mb-1 text-xl font-semibold text-text">Members</h1>
        <p className="text-sm text-text-muted">
          Who can see and approve for {activeOrg.name}.
        </p>
      </div>
      {notice && <p className="text-sm text-ok">{notice}</p>}
      {error ? (
        <ApiErrorView error={error} />
      ) : members === null ? (
        <Loading />
      ) : (
        <Card title={`${activeOrg.name} · ${members.length}`}>
          <MemberList
            members={members}
            selfId={user?.id ?? null}
            canManage={canManage}
            onRemove={(userId) => {
              setNotice("");
              api
                .removeMember(activeOrg.id, userId)
                .then(() => {
                  setNotice("Member removed. Their sessions stop now.");
                  void reload();
                })
                .catch((err: unknown) => setError(err));
            }}
            onTransfer={(userId) => {
              setNotice("");
              api
                .transferOwnership(activeOrg.id, userId)
                .then(() => {
                  setNotice("Ownership transferred.");
                  void reload();
                })
                .catch((err: unknown) => setError(err));
            }}
          />
        </Card>
      )}
      {canManage && (
        <Card title="Invite a teammate">
          <InviteForm
            onInvite={(email, inviteRole) => {
              setNotice("");
              api
                .inviteMember(activeOrg.id, email, inviteRole)
                .then((out) => {
                  setNotice(`Invite created (token ${out.invite.token}).`);
                  void reload();
                })
                .catch((err: unknown) => setError(err));
            }}
          />
        </Card>
      )}
      {isOwner && (
        <Card title="Danger zone">
          <button
            type="button"
            onClick={() => {
              api
                .deleteOrg(activeOrg.id)
                .then(() => setNotice("Organization deleted."))
                .catch((err: unknown) => setError(err));
            }}
            className="cursor-pointer rounded-lg border border-crit/40 px-3 py-1.5 text-sm text-crit outline-none hover:bg-crit/10 focus-visible:ring-2 focus-visible:ring-crit"
          >
            Delete {activeOrg.name}
          </button>
        </Card>
      )}
    </main>
  );
}
