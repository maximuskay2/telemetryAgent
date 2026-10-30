// Session + org context (C-N3, C-N6, C-N7). The API behind it is
// §8.4 in all modes: mock (NEXT_PUBLIC_COMMERCE_MOCK=1, dev-only),
// Clerk (NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY set), or a pasted test
// JWT for local dev against TA_AUTH_TEST_ISSUER backends.
"use client";

import { useAuth, useUser } from "@clerk/nextjs";
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

export const clerkPublishableKey =
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";

export type SessionUser = { id: string; email: string; name: string };

export type SessionState = {
  status: "loading" | "signed-out" | "signed-in";
  /** True only for the dev mock; never in a real build. */
  devMode: boolean;
  /** True when Clerk owns sign-in (key configured). */
  clerkMode: boolean;
  user: SessionUser | null;
  orgs: Org[];
  activeOrg: Org | null;
  role: Role | null;
  signInDev: (email: string) => Promise<void>;
  /** Local-dev override: sign in with a pasted test JWT. */
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

function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Private mode: session lasts this visit.
  }
}

function clearStored(): void {
  try {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(ORG_KEY);
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing persisted; nothing to clear.
  }
}

function pickActiveOrg(orgs: Org[]): string | null {
  const saved = readStored(ORG_KEY);
  if (saved && orgs.some((o) => o.id === saved)) return saved;
  return orgs[0]?.id ?? null;
}

function useOrgState(api: CommerceApi) {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [activeOrgId, setActiveOrgId] = useState<string | null>(null);
  const switchOrg = useCallback(
    (orgId: string) => {
      if (!orgs.some((o) => o.id === orgId)) return;
      setActiveOrgId(orgId);
      writeStored(ORG_KEY, orgId);
      if (api instanceof MockCommerceApi) {
        const found = orgs.find((o) => o.id === orgId);
        if (found) api.role = found.role;
      }
    },
    [orgs, api],
  );
  const activeOrg = orgs.find((o) => o.id === activeOrgId) ?? null;
  return {
    orgs,
    setOrgs,
    activeOrg,
    role: activeOrg?.role ?? null,
    adoptOrgs: (mine: Org[]) => {
      setOrgs(mine);
      setActiveOrgId(pickActiveOrg(mine));
    },
    resetOrgs: () => {
      setOrgs([]);
      setActiveOrgId(null);
    },
    switchOrg,
  };
}

async function notMock(): Promise<never> {
  throw new Error("Sign-in isn't connected yet.");
}

/** Dev mock (NEXT_PUBLIC_COMMERCE_MOCK=1): local sign-in, fake orgs. */
function MockSessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] =
    useState<SessionState["status"]>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);
  const api = useMemo<CommerceApi>(() => new MockCommerceApi(), []);
  const orgState = useOrgState(api);

  useEffect(() => {
    const stored = loadStored();
    if (stored) {
      setUser(stored.user);
      orgState.adoptOrgs(stored.orgs);
      setStatus("signed-in");
    } else {
      setStatus("signed-out");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signInDev = useCallback(async (email: string) => {
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
    writeStored(SESSION_KEY, JSON.stringify({ user: next, orgs: nextOrgs }));
    writeStored(ORG_KEY, nextOrgs[0].id);
    setUser(next);
    orgState.adoptOrgs(nextOrgs);
    setStatus("signed-in");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signOut = useCallback(() => {
    clearStored();
    setUser(null);
    orgState.resetOrgs();
    setStatus("signed-out");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value: SessionState = {
    status,
    devMode: true,
    clerkMode: false,
    user,
    orgs: orgState.orgs,
    activeOrg: orgState.activeOrg,
    role: orgState.role,
    signInDev,
    signInToken: notMock,
    signOut,
    switchOrg: orgState.switchOrg,
    api,
  };
  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

/** Pasted test JWT (no Clerk key): local dev against a test backend. */
function TokenSessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] =
    useState<SessionState["status"]>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const api = useMemo<CommerceApi>(
    () => new CommerceClient({ getToken: () => token }),
    [token],
  );
  const orgState = useOrgState(api);

  const bootstrapToken = useCallback(
    async (jwt: string) => {
      const who = tokenUser(jwt);
      if (!who) throw new Error("That doesn't look like a session token.");
      const client = new CommerceClient({ getToken: () => jwt });
      const { orgs: mine } = await client.listOrgs();
      writeStored(TOKEN_KEY, jwt);
      setUser(who);
      orgState.adoptOrgs(mine);
      setToken(jwt);
      setStatus("signed-in");
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  useEffect(() => {
    const stored = readStored(TOKEN_KEY);
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
  }, [bootstrapToken]);

  const signInToken = useCallback(
    async (jwt: string) => {
      const clean = jwt.trim();
      if (!clean) throw new Error("Paste a session token.");
      await bootstrapToken(clean);
    },
    [bootstrapToken],
  );

  const signOut = useCallback(() => {
    clearStored();
    setUser(null);
    orgState.resetOrgs();
    setToken(null);
    setStatus("signed-out");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value: SessionState = {
    status,
    devMode: false,
    clerkMode: false,
    user,
    orgs: orgState.orgs,
    activeOrg: orgState.activeOrg,
    role: orgState.role,
    signInDev: notMock,
    signInToken,
    signOut,
    switchOrg: orgState.switchOrg,
    api,
  };
  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

/** Clerk owns sign-in; a pasted test JWT overrides it for local dev. */
function ClerkSessionProvider({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken, signOut: clerkSignOut } = useAuth();
  const { user: clerkUser } = useUser();
  const [status, setStatus] =
    useState<SessionState["status"]>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);
  const [clerkToken, setClerkToken] = useState<string | null>(null);
  const [override, setOverride] = useState<string | null>(null);
  const token = override ?? clerkToken;
  const api = useMemo<CommerceApi>(
    () => new CommerceClient({ getToken: () => token }),
    [token],
  );
  const orgState = useOrgState(api);

  const hydrate = useCallback(
    async (jwt: string, who: SessionUser) => {
      const client = new CommerceClient({ getToken: () => jwt });
      const { orgs: mine } = await client.listOrgs();
      setUser(who);
      orgState.adoptOrgs(mine);
      setStatus("signed-in");
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Local override first (explicit), else the Clerk session.
  useEffect(() => {
    const stored = readStored(TOKEN_KEY);
    if (stored && tokenUser(stored)) {
      setOverride(stored);
      hydrate(stored, tokenUser(stored) as SessionUser).catch(() => {
        try {
          localStorage.removeItem(TOKEN_KEY);
        } catch {
          // Nothing persisted; nothing to clear.
        }
        setOverride(null);
        setStatus("signed-out");
      });
      return;
    }
    if (!isLoaded) return;
    if (!isSignedIn) {
      setStatus("signed-out");
      return;
    }
    let cancelled = false;
    getToken()
      .then((jwt) => {
        if (cancelled || !jwt) {
          if (!cancelled) setStatus("signed-out");
          return;
        }
        setClerkToken(jwt);
        const email = clerkUser?.primaryEmailAddress?.emailAddress ?? "";
        return hydrate(jwt, {
          id: clerkUser?.id ?? "",
          email,
          name: email.split("@")[0] || (clerkUser?.id ?? ""),
        });
      })
      .catch(() => {
        if (!cancelled) setStatus("signed-out");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, isSignedIn]);

  // Clerk session tokens are short-lived: refresh while signed in.
  useEffect(() => {
    if (override || !isSignedIn) return;
    const timer = setInterval(() => {
      getToken().then((jwt) => {
        if (jwt) setClerkToken(jwt);
      }).catch(() => {
        // Keep the current token; the next request 401s honestly.
      });
    }, 50000);
    return () => clearInterval(timer);
  }, [override, isSignedIn, getToken]);

  const signInToken = useCallback(
    async (jwt: string) => {
      const clean = jwt.trim();
      if (!clean) throw new Error("Paste a session token.");
      const who = tokenUser(clean);
      if (!who) throw new Error("That doesn't look like a session token.");
      writeStored(TOKEN_KEY, clean);
      setOverride(clean);
      await hydrate(clean, who);
    },
    [hydrate],
  );

  const signOut = useCallback(() => {
    clearStored();
    setUser(null);
    orgState.resetOrgs();
    setClerkToken(null);
    setOverride(null);
    setStatus("signed-out");
    void clerkSignOut();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clerkSignOut]);

  const value: SessionState = {
    status,
    devMode: false,
    clerkMode: true,
    user,
    orgs: orgState.orgs,
    activeOrg: orgState.activeOrg,
    role: orgState.role,
    signInDev: notMock,
    signInToken,
    signOut,
    switchOrg: orgState.switchOrg,
    api,
  };
  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const devMode = process.env.NEXT_PUBLIC_COMMERCE_MOCK === "1";
  if (devMode) return <MockSessionProvider>{children}</MockSessionProvider>;
  if (clerkPublishableKey !== "") {
    return <ClerkSessionProvider>{children}</ClerkSessionProvider>;
  }
  return <TokenSessionProvider>{children}</TokenSessionProvider>;
}

export function useSession(): SessionState {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession needs SessionProvider");
  return session;
}
