/** Device-specific pairing URLs from one server pairing URL (M1).

`/api/pairing` returns the URL for a physical phone on the same Wi-Fi (a
LAN IP in local dev, the public domain when hosted). That one string is
wrong on other devices: an Android emulator must use the host-loopback
alias 10.0.2.2, and localhost only works on the API machine itself.
`pairingVariants` derives the right URL per device so every pairing
screen can offer the one that actually connects.
*/
export type PairTarget = "phone" | "emulator" | "computer";

export interface PairingVariant {
  target: PairTarget;
  label: string;
  hint: string;
  url: string;
  /** True when the server could not detect a reachable address. */
  unreachable: boolean;
}

const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;

export function pairingVariants(apiUrl: string): PairingVariant[] {
  const phone: PairingVariant = {
    target: "phone",
    label: "Physical phone",
    hint: "same Wi-Fi",
    url: apiUrl,
    unreachable: false,
  };
  let parsed: URL;
  try {
    parsed = new URL(apiUrl);
  } catch {
    return [phone];
  }
  // Hosted domain: one URL fits every device, no variants to derive.
  if (!IPV4.test(parsed.hostname)) return [phone];
  const withHost = (host: string): string => {
    const swapped = new URL(parsed.toString());
    swapped.hostname = host;
    return swapped.toString().replace(/\/$/, "");
  };
  const loopback =
    parsed.hostname === "127.0.0.1" || parsed.hostname === "::1";
  return [
    {
      ...phone,
      hint: loopback
        ? "API could not detect its LAN IP — use the emulator entry"
        : "same Wi-Fi",
      unreachable: loopback,
    },
    {
      target: "emulator",
      label: "Android emulator",
      hint: "host loopback alias",
      url: withHost("10.0.2.2"),
      unreachable: false,
    },
    {
      target: "computer",
      label: "This computer",
      hint: "app + API on this machine",
      url: withHost("localhost"),
      unreachable: false,
    },
  ];
}
