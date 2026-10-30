# John status (commercial)
Current block: Sales-ready look DONE (merged) — waiting on commercial-contracts-in for Phase 1 web/app
Done: Sales-ready look (this branch, merged to main)
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
Contract changes requested: —
Live runs (lang · result · seconds · model): —
NEEDS FROM AKINGBADE: —
BLOCKED: —
