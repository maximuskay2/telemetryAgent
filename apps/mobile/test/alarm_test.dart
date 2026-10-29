import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telemetry_agent/models/agent_step.dart';
import 'package:telemetry_agent/models/pending_action.dart';
import 'package:telemetry_agent/models/run_report.dart';
import 'package:telemetry_agent/providers.dart';
import 'package:telemetry_agent/screens/alarm_screen.dart';
import 'package:telemetry_agent/services/alarm.dart';

PendingAction _action() => PendingAction(
      runId: 'r-1',
      domain: 'software',
      action: 'Deploy the verified inventory patch to the shop',
      openedAt: 1000,
      deadline: DateTime.now().millisecondsSinceEpoch / 1000 + 20,
    );

void main() {
  group('AlarmScreen', () {
    testWidgets('shows countdown, summary, and all buttons',
        (tester) async {
      tester.view.physicalSize = const Size(800, 4000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      bool? decided;
      bool? marked;
      await tester.pumpWidget(
        MaterialApp(
          home: AlarmScreen(
            action: _action(),
            secondsLeft: 17,
            onDecide: (approve, markNormal) async {
              decided = approve;
              marked = markNormal;
            },
            onSilence: () async {},
          ),
        ),
      );
      expect(find.text('VETO WINDOW OPEN'), findsOneWidget);
      expect(find.text('17s'), findsOneWidget);
      expect(find.textContaining('Deploy the verified'), findsOneWidget);
      await tester.tap(find.text('DISAPPROVE'));
      expect(decided, isFalse);
      expect(marked, isFalse);
      await tester.tap(find.text('Disapprove + this is normal'));
      expect(decided, isFalse);
      expect(marked, isTrue);
      await tester.tap(find.text('Approve now'));
      expect(decided, isTrue);
      expect(marked, isFalse);
    });

    testWidgets('busy disables the buttons and shows the error',
        (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: AlarmScreen(
            action: _action(),
            secondsLeft: 3,
            onDecide: (_, _) async {},
            onSilence: () async {},
            busy: true,
            error: 'Too late — the server already decided.',
          ),
        ),
      );
      await tester.scrollUntilVisible(
        find.textContaining('Too late'),
        200,
      );
      expect(find.textContaining('Too late'), findsOneWidget);
      final off = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, '…'),
      );
      expect(off.onPressed, isNull);
    });
  });

  group('AlarmScreen context', () {
    testWidgets('approval-only variant shows diagnosis and evidence',
        (tester) async {
      tester.view.physicalSize = const Size(800, 4000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      final action = PendingAction(
        runId: 'r-2',
        domain: 'software',
        action: 'Deploy the verified inventory patch',
        openedAt: 1000,
        deadline:
            DateTime.now().millisecondsSinceEpoch / 1000 + 20,
        autoApply: false,
      );
      const report = RunReport(
        runId: 'r-2',
        domain: 'software',
        status: 'PASS',
        steps: [
          AgentStep(
              step: 'diagnose', detail: 'Lock order bug in inventory'),
          AgentStep(step: 'generate', attempt: 1),
          AgentStep(step: 'verify', status: 'PASS'),
          AgentStep(step: 'done', status: 'PASS'),
        ],
        verification: {
          'runner': 'docker',
          'original': {'passed': false, 'output': 'x'},
          'patched': {'passed': true, 'output': 'y'},
        },
      );
      await tester.pumpWidget(
        MaterialApp(
          home: AlarmScreen(
            action: action,
            secondsLeft: 14,
            report: report,
            onDecide: (_, _) async {},
            onSilence: () async {},
          ),
        ),
      );
      expect(find.text('APPROVAL REQUIRED'), findsOneWidget);
      expect(find.text('nothing applies without you'), findsOneWidget);
      expect(find.text('Lock order bug in inventory'), findsOneWidget);
      expect(
          find.text('Verified: tests fail→pass in docker'),
          findsOneWidget);
      expect(find.text('SUGGEST'), findsOneWidget);
    });
  });

  group('correctedSecondsLeft', () {
    test('fresh tick wins, stale tick falls back to deadline', () {
      final now = DateTime.fromMillisecondsSinceEpoch(1010 * 1000);
      final action = PendingAction(
        runId: 'r',
        domain: 'software',
        action: 'Deploy',
        openedAt: 1000,
        deadline: 1020,
      );
      expect(correctedSecondsLeft(action, null, now), 10);
      final fresh = ServerTick(
          'r', 8, DateTime.fromMillisecondsSinceEpoch(1009 * 1000));
      expect(correctedSecondsLeft(action, fresh, now), 7);
      final stale = ServerTick(
          'r', 18, DateTime.fromMillisecondsSinceEpoch(1000 * 1000));
      expect(correctedSecondsLeft(action, stale, now), 10);
      final other = ServerTick(
          'other', 1, DateTime.fromMillisecondsSinceEpoch(1010 * 1000));
      expect(correctedSecondsLeft(action, other, now), 10);
    });
  });

  group('OutcomeScreen', () {
    testWidgets('titles match the decision states', (tester) async {
      PendingAction actionWith(String state) => PendingAction(
            runId: 'r',
            domain: 'software',
            action: 'Deploy the patch',
            openedAt: 1000,
            deadline: 1020,
            state: state,
            detail: 'applied by pixel',
          );
      await tester.pumpWidget(
        MaterialApp(
            home: OutcomeScreen(action: actionWith('disapproved'))),
      );
      expect(find.text('Disapproved — left for a human'), findsOneWidget);
      expect(find.text('applied by pixel'), findsOneWidget);
      await tester.pumpWidget(
        MaterialApp(
            home: OutcomeScreen(action: actionWith('auto_applied'))),
      );
      expect(find.text('Auto-applied ✓'), findsOneWidget);
      await tester.pumpWidget(
        MaterialApp(
            home: OutcomeScreen.tooLate(action: actionWith('pending'))),
      );
      expect(find.text('Too late — already applied'), findsOneWidget);
    });
  });

  group('AlarmHardware', () {
    test('disabled hardware never touches the platform', () async {
      final hardware = AlarmHardware(enabled: false);
      await hardware.ring();
      expect(hardware.ringing, isFalse);
      await hardware.stop();
    });

    test('stop is safe when nothing rang', () async {
      final hardware = AlarmHardware(enabled: false);
      await hardware.stop();
      await AlarmHardware.cancel(_action());
    });
  });
}
