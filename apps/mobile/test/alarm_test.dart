import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telemetry_agent/models/pending_action.dart';
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
    testWidgets('shows countdown, summary, and both buttons',
        (tester) async {
      bool? decided;
      await tester.pumpWidget(
        MaterialApp(
          home: AlarmScreen(
            action: _action(),
            secondsLeft: 17,
            onDecide: (approve) async => decided = approve,
            onSilence: () async {},
          ),
        ),
      );
      expect(find.text('VETO WINDOW OPEN'), findsOneWidget);
      expect(find.text('17s'), findsOneWidget);
      expect(find.textContaining('Deploy the verified'), findsOneWidget);
      await tester.tap(find.text('DISAPPROVE'));
      expect(decided, isFalse);
      await tester.tap(find.text('APPROVE'));
      expect(decided, isTrue);
    });

    testWidgets('busy disables the buttons and shows the error',
        (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: AlarmScreen(
            action: _action(),
            secondsLeft: 3,
            onDecide: (_) async {},
            onSilence: () async {},
            busy: true,
            error: 'Too late — the server already decided.',
          ),
        ),
      );
      expect(find.textContaining('Too late'), findsOneWidget);
      final off = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, '…'),
      );
      expect(off.onPressed, isNull);
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
