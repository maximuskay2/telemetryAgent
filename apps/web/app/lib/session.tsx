// Session + org context (C-N3, C-N6). The API behind it is §8.4 in
// both modes: mock (NEXT_PUBLIC_COMMERCE_MOCK=1, dev-only) or HTTP
// against the real backend. Real sign-in takes a Clerk session JWT
// once keys land (see NEEDS); until then a pasted test JWT signs in
// local dev against TA_AUTH_TEST_ISSUER backends only.
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  CommerceApi,
  CommerceClient,
  Org,
  Role,
} from "./commerce";
import { MockCommerceApi } from "./commerce-mock";

export type SessionUser = { id: string; email: string; name: string };

export type SessionState = {
  status: "loading" | "signed-out" | "signed-in";
  /** True only for the dev mock; never in a real build. */
  devMode: boolean;
  user: SessionUser | null;
  orgs: Org[];
  activeOrg: Org | null;
  role: Role | null;
  signInDev: (email: string) => Promise<void>;
  /** Local-dev only: sign in with a pasted test JWT (no Clerk yet). */
  signInToken: (token: string) => Promise<void>;
  signOut: () => void;
  switchOrg: (orgId: string) => void;
  api: CommerceApi;
};

const SessionContext = createContext<SessionState | null>(null);

const SESSION_KEY = "ta-session";
const ORG_KEY = "ta-org";
const TOKEN_KEY = "ta-token";

/** Display-only JWT payload read (the backend verifies the signature). */
function tokenUser(token: string): SessionUser | null {
  try {
    const payload = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    ) as { sub?: string; email?: string };
    if (!payload.sub) return null;
    const email = payload.email ?? "";
    return {
      id: payload.sub,
      email,
      name: email.split("@")[0] || payload.sub,
    };
  } catch {
    return null;
  }
}

function loadStored(): { user: SessionUser; orgs: Org[] } | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as {
      user?: SessionUser;
      orgs?: Org[];
    };
    if (!parsed.user || !Array.isArray(parsed.orgs)) return null;
    return { user: parsed.user, orgs: parsed.orgs };
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const devMode = process.env.NEXT_PUBLIC_COMMERCE_MOCK === "1";
  const [status, setStatus] =
    useState<SessionState["status"]>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [activeOrgId, setActiveOrgId] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  const api = useMemo<CommerceApi>(() => {
    if (devMode) return new MockCommerceApi();
    return new CommerceClient({ getToken: () => token });
  }, [devMode, token]);

  const bootstrapToken = useCallback(async (jwt: string) => {
    const who = tokenUser(jwt);
    if (!who) throw new Error("That doesn't look like a session token.");
    const client = new CommerceClient({ getToken: () => jwt });
    const { orgs: mine } = await client.listOrgs();
    try {
      localStorage.setItem(TOKEN_KEY, jwt);
    } catch {
      // Private mode: session lasts this visit.
    }
    let savedOrg: string | null = null;
    try {
      savedOrg = localStorage.getItem(ORG_KEY);
    } catch {
      savedOrg = null;
    }
    setUser(who);
    setOrgs(mine);
    setToken(jwt);
    setActiveOrgId(
      savedOrg && mine.some((o) => o.id === savedOrg)
        ? savedOrg
        : (mine[0]?.id ?? null),
    );
    setStatus("signed-in");
  }, []);

  useEffect(() => {
    if (!devMode) {
      let stored: string | null = null;
      try {
        stored = localStorage.getItem(TOKEN_KEY);
      } catch {
        stored = null;
      }
      if (!stored) {
        setStatus("signed-out");
        return;
      }
      bootstrapToken(stored).catch(() => {
        try {
          localStorage.removeItem(TOKEN_KEY);
        } catch {
          // Nothing persisted; nothing to clear.
        }
        setStatus("signed-out");
      });
      return;
    }
    const stored = loadStored();
    if (stored) {
      setUser(stored.user);
      setOrgs(stored.orgs);
      setToken("dev-token");
      const savedOrg = (() => {
        try {
          return localStorage.getItem(ORG_KEY);
        } catch {
          return null;
        }
      })();
      setActiveOrgId(
        savedOrg && stored.orgs.some((o) => o.id === savedOrg)
          ? savedOrg
          : (stored.orgs[0]?.id ?? null),
      );
      setStatus("signed-in");
    } else {
      setStatus("signed-out");
    }
  }, [devMode]);

  const signInDev = useCallback(
    async (email: string) => {
      if (!devMode) throw new Error("Sign-in isn't connected yet.");
      const clean = email.trim();
      if (!clean || !clean.includes("@")) {
        throw new Error("Enter an email address.");
      }
      const next: SessionUser = {
        id: "usr_dev",
        email: clean,
        name: clean.split("@")[0] || "Dev",
      };
      const nextOrgs: Org[] = [
        { id: "org_acme", name: "Acme", role: "owner" },
        { id: "org_demo", name: "Demo", role: "viewer" },
      ];
      try {
        localStorage.setItem(
          SESSION_KEY,
          JSON.stringify({ user: next, orgs: nextOrgs }),
        );
        localStorage.setItem(ORG_KEY, nextOrgs[0].id);
      } catch {
        // Private mode: session lasts this visit.
      }
      setUser(next);
      setOrgs(nextOrgs);
      setActiveOrgId(nextOrgs[0].id);
      setToken("dev-token");
      setStatus("signed-in");
    },
    [devMode, bootstrapToken],
  );

  const signInToken = useCallback(
    async (jwt: string) => {
      const clean = jwt.trim();
      if (!clean) throw new Error("Paste a session token.");
      await bootstrapToken(clean);
    },
    [bootstrapToken],
  );

  const signOut = useCallback(() => {
    try {
      localStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(ORG_KEY);
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      // Nothing persisted; nothing to clear.
    }
    setUser(null);
    setOrgs([]);
    setActiveOrgId(null);
    setToken(null);
    setStatus("signed-out");
  }, []);

  const switchOrg = useCallback(
    (orgId: string) => {
      if (!orgs.some((o) => o.id === orgId)) return;
      setActiveOrgId(orgId);
      try {
        localStorage.setItem(ORG_KEY, orgId);
      } catch {
        // Session lasts this visit.
      }
      if (api instanceof MockCommerceApi) {
        const found = orgs.find((o) => o.id === orgId);
        if (found) api.role = found.role;
      }
    },
    [orgs, api],
  );

  const activeOrg = orgs.find((o) => o.id === activeOrgId) ?? null;
  const value: SessionState = {
    status,
    devMode,
    user,
    orgs,
    activeOrg,
    role: activeOrg?.role ?? null,
    signInDev,
    signInToken,
    signOut,
    switchOrg,
    api,
  };
  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession needs SessionProvider");
  return session;
}
