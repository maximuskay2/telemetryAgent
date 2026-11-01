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
