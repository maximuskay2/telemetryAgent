const PRODUCTION_API = "https://api-production-0c9a.up.railway.app";

function resolveApiUrl(): string {
  const explicit = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
  const leftoverLocal =
    !explicit ||
    explicit.includes("localhost") ||
    explicit.includes("127.0.0.1");
  if (leftoverLocal && process.env.NODE_ENV === "production") {
    return PRODUCTION_API;
  }
  return explicit || "http://localhost:8000";
}

export const apiUrl = resolveApiUrl();

export async function responseDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    // fall through to the status-based message
  }
  return `API returned ${response.status}`;
}

export function wsUrl(): string {
  return `${apiUrl.replace(/^http/, "ws")}/api/ws`;
}
