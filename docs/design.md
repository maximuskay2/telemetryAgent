# Classic palette — design notes

Source of truth for tokens: `apps/web/app/tokens.css`. These are the
pre-redesign dashboard colors (mint green on near-black). The phone copies the
same hex values into `apps/mobile/lib/theme.dart`.

## Colour tokens

| Token | Hex | Use |
| --- | --- | --- |
| `bg` | `#0B0E10` | App background |
| `surface` | `#111719` | Cards, panes |
| `surface-2` | `#0D1314` | Drawers, popovers, hovered cards |
| `border` | `#252D2F` | Hairlines |
| `text` / `text-muted` / `text-faint` | `#E7EEEA` / `#879694` / `#667371` | Primary / labels / timestamps |
| `brand` / `brand-cyan` | `#A5EFC0` / `#A5EFC0` | AI activity, links, focus rings |
| `ok` | `#A5EFC0` | Verified PASS, healthy, ignored normal behaviour |
| `warn` | `#F3CF7E` | Gate observe, warnings, countdown middle |
| `crit` | `#FF887F` | Active incidents, deadlocks, hard limits, countdown last 5 s |
| ink on bright buttons | `#0B1710` | Text on mint/green/red fills |

Badge backgrounds use a 12% tint, borders/glows a 40% tint
(Tailwind: `bg-ok/10`, `border-ok/40`, …). All text pairs meet WCAG AA.

## Status vocabulary (exact words)

Healthy / Normal · ignored / Observing / Incident / Hard limit /
Learning / Setup needed, plus the model name for AI activity.
Every status is colour **+ icon + word** (see `STATUS` in `app/ui/Badge.tsx`).

## Do / don't

- Do write sentences ("Ignored: expected defrost (spec sheet p.2)").
- Do label the trace "Agent trace" and passed fixes "verified fix".
- Don't use red for anything but real incidents, hard limits, and the
  countdown's last 5 seconds.
- Don't invent motion: every pulse, dot, and tick comes from a real event,
  and everything respects `prefers-reduced-motion`.
- Don't add `NEXT_PUBLIC_*` secrets to the web bundle.

## Screenshots

![Mission Control](screenshots/mission.png)
![Setup wizard](screenshots/setup.png)
![Incident report](screenshots/incident.png)
![Shop storefront](screenshots/shop.png)
