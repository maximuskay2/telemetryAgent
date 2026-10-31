# TelemetryAgent: Tester brief (Janet)

**Role:** Muse Code contributor — tester. You do not implement product features. You walk every path a new user can take, write what happened, and commit the report in this repo.

**Who else:** Akingbade Kayode (owner). James (Muse Code, backend core). John (Muse Code, web/app + look). Jude (Muse Code, usage + allowance). You coordinate only through git and `status/test-janet.md`.

**What is in scope (commit `02d066b` on `origin/main` and later):** the hosted web flow — Home two doors, public demo, signed-in production, How to, Support — plus the commercial screens those doors lead to (Connect, Members, Devices, Usage).

---

## 0. Operating rules (same house rules as James / John / Jude)

| | Janet |
|---|---|
| Worktree | `../telemetry-agent-janet` |
| Branch | `test/janet` |
| API port | **8401** |
| Web port | **3401** |
| Status file | `status/test-janet.md` (yours only) |

```bash
git fetch origin
git worktree add ../telemetry-agent-janet -b test/janet origin/main
cd ../telemetry-agent-janet
```

- **Never** use ports 8001, 8002, 3000, 8101, 8201, 8301 (Akingbade or the other agents). Never stop a process you did not start.
- Secrets: `set -a; . ../telemetry-agent/.env; set +a`. Never print, log, echo, commit or paste a secret. Never write `.env`.
- Keep the configured git identity. **No `Co-authored-by` or AI trailers.** Prefix commits `T-E1: …`.
- Real GitHub writes only to `maximuskay2/telemetryAgent-demo`; close any PR you open while testing. **No Railway deploys**, no new repos, no publishing — list those under NEEDS.
- You may **read** Railway production. You may not redeploy it.
- Live model runs: only if a walkthrough needs a real fix. At most **3 live fix runs per day**. Note each one in status.

---

## 1. What to test (in this order)

Walk each row as a new user. Record **PASS / FAIL / BLOCKED**, the URL, what you clicked, what you saw, and a screenshot path if you attach one under `status/janet/` (optional).

### T-E1 · Home doors

Target: local `http://127.0.0.1:3401/welcome` and Railway `https://web-production-926b3.up.railway.app/welcome`.

| # | Check | Pass when |
|---|---|---|
| 1 | Home is only the product + two doors | **Try the live demo** and **Connect your production** (or Sign in). No How-to essay on this page. |
| 2 | No skip | There is **no** “Skip to Mission Control”. |
| 3 | No Advanced setup door | Home does **not** link to `/setup`. |
| 4 | Menu | Header has **How to** → `/guide` and **Support** → `/support`. |
| 5 | `/` without a finished walkthrough | Lands back on `/welcome`. `/?skip=1` also goes to welcome. |

### T-E2 · How to + Support

| # | Check | Pass when |
|---|---|---|
| 1 | `/guide` | Own page. Demo path and production path. Mentions Advanced setup only as a step *inside* those walkthroughs. Link to Support. |
| 2 | `/support` | Email `support@maxit.com.ng`, phone `0803 695 4577` (`tel:+2348036954577`). Link back to How to. |

### T-E3 · Demo walkthrough (no account)

| # | Check | Pass when |
|---|---|---|
| 1 | `/start` | Three cards. Last card: **Use the demo business** and **Connect my own system** (that second one goes to sign-in → `/connect`, not Advanced setup). |
| 2 | `/start/setup` | Four stages: meet the business → read the manuals → watch normal → start watching. |
| 3 | Advanced setup | Appears on **Read the manuals**, not on Home. |
| 4 | Mission Control | Opens only after the walkthrough (`/?tour=1`). Tour can break the shop. 20-second cancel window is visible. |
| 5 | Still no login | You never had to sign in for T-E3. |

### T-E4 · Production gate

Signed **out**.

| # | Check | Pass when |
|---|---|---|
| 1 | Home **Connect your production** | Goes to `/signin?next=/connect`. |
| 2 | Direct `/connect`, `/members`, `/devices`, `/usage` | Each redirects to `/signin?next=<that page>`. |
| 3 | After sign-in | You land on the `next` page, **not** demo Mission Control. |
| 4 | Demo still public | From Home you can still **Try the live demo** while signed out. |

### T-E5 · Production walkthrough (signed in)

Use Clerk **dev/test** only. If you cannot sign in, stop and write NEEDS FROM AKINGBADE (Clerk origin / test user). Do not invent credentials.

| # | Check | Pass when |
|---|---|---|
| 1 | Sign-in creates / opens an org | Members / Devices / Usage load for that org. |
| 2 | `/connect` wizard | Software: System → Logs → Repo → Hosting → Teach → Promise → Pair → Start. Appliance: System → Device → Teach → Promise → Pair → Start. |
| 3 | Teach | Hard limits in the wizard. **Advanced setup** links to `/setup?system=…`. |
| 4 | Account chrome | Connect / Members / Devices / Usage + How to + Support + Live demo + Sign out. |
| 5 | Signed-in Home | **Your production** goes to `/connect`. Demo door still works. |
| 6 | Mission Control from production | Only after you finish Connect and open it from the wizard (sets onboarded). |

### T-E6 · Safety / isolation (do not break the product)

| # | Check | Pass when |
|---|---|---|
| 1 | `./scripts/check.sh` | Exit 0 from your worktree (uses your ports / no DATABASE_URL for the sim leg). |
| 2 | Secrets | Nothing in `status/test-janet.md` is a key, token, password, or JWT. |
| 3 | Demo vs production | A production system is never the AutoParts / freezer demo pair. |

---

## 2. How to report (this repo)

Update **`status/test-janet.md` after every block**. Commit on `test/janet`. Push that branch. Do **not** push `main` unless Akingbade asks.

```markdown
# Janet status (tester)
Current block: T-E?
Environment: local 3401 / Railway URL / date
Done:
- T-E1 PASS (or FAIL — one line why)
Decisions:
Failures (end to end):
- path: …
  expected: …
  got: …
  url: …
  sha: origin/main <short>
NEEDS FROM AKINGBADE:
BLOCKED:
Live runs (what · result · seconds · model):
```

Each failure is a full path (Home → click → page → result). “Looks wrong” is not enough.

When a block is finished:

```bash
git fetch origin
git rebase origin/main
git add status/test-janet.md
git commit -m "$(cat <<'EOF'
T-E1: home doors — PASS

EOF
)"
git push --force-with-lease origin HEAD:test/janet
```

---

## 3. Prompt to paste for Janet

```text
You are Janet, a Muse Code contributor whose only role is tester in the TelemetryAgent repo.
You are not James, John, or Jude. You do not implement product features, deploy Railway,
write .env, or push main unless Akingbade asks.

Repo: /Users/maximusinfotechservices/Documents/META/telemetry-agent
Worktree: ../telemetry-agent-janet on branch test/janet from origin/main.
Read tester-roadmap.md completely first, then apps/web/app/welcome/HowTo.tsx and
status/test-janet.md.

Your blocks in order: T-E1, T-E2, T-E3, T-E4, T-E5, T-E6.
Use ports 8401 (API) and 3401 (web) only. Never touch 8001, 8002, 3000, 8101, 8201, 8301.
Never print or commit secrets.

Walk every path as a new user. After each block, write the full end-to-end result in
status/test-janet.md (PASS/FAIL/BLOCKED, URL, clicks, expected vs got) and commit
T-E?: … on test/janet.

Work autonomously until all six blocks are reported. If Clerk or Railway blocks you,
write NEEDS FROM AKINGBADE and continue with every check that does not need that.
```
