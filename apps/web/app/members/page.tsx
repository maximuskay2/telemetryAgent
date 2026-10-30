// Members (C-N3): list, invite, remove, transfer, delete org.
"use client";

import { useCallback, useEffect, useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { CommerceError, Member } from "../lib/commerce";
import { useSession } from "../lib/session";
import { Card } from "../ui";
import {
  ApiErrorView,
  InviteForm,
  Loading,
  MemberList,
  OrgSwitcher,
} from "../commerce/components";

export default function MembersPage() {
  const { status, user, orgs, activeOrg, role, api, switchOrg } = useSession();
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

  if (status === "loading") {
    return (
      <main className="mx-auto w-full max-w-2xl px-4 py-8">
        <Loading />
      </main>
    );
  }
  if (status === "signed-out" || !activeOrg) {
    return (
      <main className="mx-auto w-full max-w-2xl space-y-4 px-4 py-8">
        <ApiErrorView error={new CommerceError(401, "Signed out")} />
      </main>
    );
  }

  const canManage = role === "owner" || role === "admin";
  const isOwner = role === "owner";

  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 px-4 py-8">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="mb-1 text-xl font-semibold text-text">Members</h1>
          <p className="text-sm text-text-muted">
            Who can see and approve for {activeOrg.name}.
          </p>
        </div>
        <ThemeToggle />
      </div>
      <OrgSwitcher orgs={orgs} activeId={activeOrg.id} onSwitch={switchOrg} />
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
