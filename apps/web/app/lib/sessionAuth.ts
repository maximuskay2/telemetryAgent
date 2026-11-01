// Shared session credentials for plain API clients (connect/api, setupApi).
// CommerceClient carries its own token; these module-level clients cannot
// use React hooks, so the owning page sets the provider from useSession.
// Default is signed-out: no headers, demo traffic unchanged.
export type SessionAuth = { token: string | null; orgId: string | null };

let provider: () => SessionAuth = () => ({ token: null, orgId: null });

export function setSessionAuthProvider(next: () => SessionAuth): void {
  provider = next;
}

export function sessionAuthHeaders(): Record<string, string> {
  const { token, orgId } = provider();
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(orgId ? { "X-Org-Id": orgId } : {}),
  };
}

let refresher: () => Promise<string | null> = async () => null;

export function setSessionAuthRefresher(
  next: () => Promise<string | null>,
): void {
  refresher = next;
}

/**
 * Mint a fresh session token (Clerk skipCache). Returns the token for
 * immediate use — React state lands a beat later, so callers must send
 * THIS value on the retry, not re-read the provider. Null when refresh
 * is impossible (signed out, override, mock): don't retry.
 */
export async function refreshSessionAuth(): Promise<string | null> {
  try {
    return await refresher();
  } catch {
    return null;
  }
}
