/** Safe in-app return path after sign-in. Rejects open redirects. */
export function safeNext(
  raw: string | null | undefined,
  fallback = "/dashboard",
): string {
  if (!raw) return fallback;
  if (!raw.startsWith("/") || raw.startsWith("//")) return fallback;
  return raw;
}

export function signInHref(next = "/dashboard"): string {
  return `/signin?next=${encodeURIComponent(safeNext(next))}`;
}
