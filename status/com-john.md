# John status (commercial)
Current block: C-N4 Phase 1 app (claim sign-in, devices, approve)
Done: C-N1+C-N2 sales look (merged 0c63127), C-N3 Phase 1 web (this branch)
§8 confirmation (for C-J0): read and accepted — building web/app against the frozen §8.4 JSON with mocks per C-6. No contract issues so far.
Decisions:
- Tokens: light `:root` default (FB wash #F0F2F5, white cards, #050505,
  #0866FF primary + white labels), dark `[data-theme=dark]` (#18191A,
  #242526, same blue). First visit with no saved choice opens light
  (spec; OS preference intentionally ignored); choice in localStorage,
  applied pre-paint by an inline script.
- Dark link/text blue is #2D88FF while primary fills stay #0866FF both
  modes: #0866FF text on #18191A is unreadable (~2.9:1), so text-only
  accents use Meta's own dark-surface blue. Documented in tokens.css.
- Status WORDS untouched (ui/Badge.tsx); light ok/warn/crit darkened
  for contrast on white, dark keeps legible values.
- Danger buttons use a fixed #D61C1C + white both modes (mode-varying
  crit can't take one label color); Buy/Apply/Veto-confirm are blue
  primaries (Meta style), `text-on-brand` labels everywhere.
- Fonts: UI `Optimistic, Helvetica, Arial, sans-serif` (CSS only —
  no Optimistic files committed, verified by test); GeistSans
  dropped (web import + mobile asset removed); GeistMono kept for
  code/logs/IDs. Mono audited: 46→26 web sites, 3 mobile
  conversions; the rest are code/logs/IDs/keys/URLs.
- `.legacy` (classic, out of scope) pinned to its dark values so the
  light default can't alter it.
- Attribution "Built with Muse Spark" (plain text, no link) on
  welcome + Mission Control web, settings screen on phone. No Meta
  or Facebook logos, names, or ownership claims anywhere (test scans
  web + mobile sources and asset filenames).
- Phone: Riverpod ThemeMode + shared_preferences persistence,
  settings switch, mode-aware palette getters (50 `const` drops,
  mechanical, analyzer-clean).
- Done-when evidence: 23 node tests + 7 flutter theme tests green;
  headless-Chrome CDP proof (fresh=light, toggle→dark, dark
  survives reload, cleared→light, 9/9) + 3 screenshots in
  docs/screenshots/ (welcome-light, mission-light, mission-dark),
  visually reviewed. Full check.sh green at merge.
Decisions (C-N3):
- No @clerk/nextjs this round: unverifiable without keys, so the
  SessionProvider exposes an AuthClient seam (dev mock now, Clerk
  later). Dev mock behind NEXT_PUBLIC_COMMERCE_MOCK=1 only; real
  mode calls §8.4 HTTP with a session JWT and degrades to honest
  401/403/empty states. Fake dev tokens can never authenticate
  (backend verifies Clerk JWT).
- Sign-in without keys shows the form disabled with a "being
  connected" notice; with the mock flag it's a working dev sign-in.
- Presentational commerce components take props (mocked render
  tests); pages are thin session wiring. OrgSwitcher is a native
  select in the TopBar account cluster + members/devices headers.
Contract changes requested: —
Live runs (lang · result · seconds · model): —
NEEDS FROM AKINGBADE: Clerk dev publishable key (web sign-in goes
live with it; backend JWKS is James's NEEDS).
BLOCKED: —
