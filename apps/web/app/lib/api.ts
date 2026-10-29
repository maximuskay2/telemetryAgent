export const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
