# Telemetry Agent (phone)

Flutter companion to the Mission Control dashboard: veto alarms that fire
over the lock screen, a live feed, and per-incident reports.

## Run

```sh
cd apps/mobile
flutter pub get
flutter run
```

The phone and the API must share Wi-Fi (start the demo with
`API_HOST=0.0.0.0`). Pair from the dashboard's QR: scan it in the app and
type the mobile token from `.env`.

## What's inside

- **Alarm** (`lib/screens/alarm_screen.dart`): full-bleed veto screen with a
  massive countdown ring driven by the server deadline, haptic ticks that
  escalate in the last 5 s, looping alarm sound, diagnosis + stepper +
  fail→pass evidence, one-tap **DISAPPROVE** / **Approve now** with lockout.
  Amber "APPROVAL REQUIRED" variant when auto-fix is off.
- **Feed + reports** (`home_screen.dart`, `report_screen.dart`): live event
  feed, incident list with §3 status badges and filters
  (All/Open/Auto-applied/Approved/Disapproved/Failed/Ignored), and reports
  with pipeline stepper, diagnosis, fix/runbook, verification evidence,
  decision record, gate verdict, swipeable temperature/current/vibration
  charts with the profile's normal band, and PR links.
- **Theme** (`lib/theme.dart`, `lib/widgets/`): Enterprise Obsidian tokens
  copied from `apps/web/app/tokens.css`, vendored Geist fonts
  (`assets/fonts/`, OFL — no runtime downloads, works offline).

## Test

```sh
flutter test
flutter analyze
```

Rehearse the alarm from Settings → Test alarm (fake 20 s window; the
server knows nothing about it).
