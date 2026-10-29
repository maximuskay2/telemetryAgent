import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telemetry_agent/widgets/action_cards.dart';

Future<void> _pumpCard(WidgetTester tester, Widget card) async {
  tester.view.physicalSize = const Size(800, 4000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: card)),
    ),
  );
}

const _remote = [
  CardOption(
    id: 'opt_defrost',
    kind: 'remote',
    title: 'Start defrost',
    detail: 'Run the defrost cycle now.',
  ),
  CardOption(
    id: 'opt_setpoint',
    kind: 'remote',
    title: 'Lower setpoint 1 °C',
    safetyOk: false,
    safetyReason: 'already at the profile minimum',
  ),
  CardOption(
    id: 'opt_backup',
    kind: 'remote',
    title: 'Switch to backup unit',
    status: 'done',
  ),
];

void main() {
  group('PrReadyCard', () {
    testWidgets('shows proof, PR, and the mitigation countdown',
        (tester) async {
      var opened = '';
      var now = 0;
      var cancelled = 0;
      await _pumpCard(
        tester,
        PrReadyCard(
          summary: 'Empty-cart total divides by zero in cart.py',
          proofLine: 'fails → passes, suite green (21 passed)',
          prUrl: 'https://github.com/acme/api/pull/7',
          onOpenPr: (url) => opened = url,
          mitigationLabel: 'Roll back now',
          mitigationDetail: 'Roll back to previous deploy',
          mitigationSecondsLeft: 14,
          onMitigateNow: () => now++,
          onCancelMitigation: () => cancelled++,
        ),
      );
      expect(find.textContaining('divides by zero'), findsOneWidget);
      expect(find.textContaining('fails → passes'), findsOneWidget);
      await tester.tap(find.text('Open PR'));
      expect(opened, 'https://github.com/acme/api/pull/7');
      expect(find.textContaining('14s'), findsOneWidget);
      await tester.tap(find.text('Roll back now'));
      expect(now, 1);
      await tester.tap(find.text('Cancel'));
      expect(cancelled, 1);
    });

    testWidgets('pending states until the backend provides them',
        (tester) async {
      await _pumpCard(
        tester,
        PrReadyCard(
          summary: 'Traceback in checkout',
          proofLine: '',
          onOpenPr: (_) {},
          onMitigateNow: () {},
          onCancelMitigation: () {},
        ),
      );
      expect(find.textContaining('PR pending'), findsOneWidget);
      expect(find.text('No mitigation proposed.'), findsOneWidget);
      expect(find.text('Open PR'), findsNothing);
    });
  });

  group('HardwareFixCard', () {
    testWidgets('groups, send, and unsafe options stay disabled',
        (tester) async {
      var executed = '';
      await _pumpCard(
        tester,
        HardwareFixCard(
          title: 'Fridge warm · run abc123',
          remote: _remote,
          manual: const [
            CardOption(
                id: 'opt_door', kind: 'manual', title: 'Close the door'),
          ],
          dispatch: const [
            CardOption(
              id: 'opt_tech',
              kind: 'dispatch',
              title: 'Call the technician',
              detail: 'WO-7 · site B, cabinet 3',
            ),
          ],
          onExecute: (id) => executed = id,
        ),
      );
      expect(find.text('REMOTE'), findsOneWidget);
      expect(find.text('ON-SITE CHECKLIST'), findsOneWidget);
      expect(find.text('TECHNICIAN'), findsOneWidget);
      expect(find.text('Start defrost'), findsOneWidget);
      expect(
        find.text('Disabled: already at the profile minimum'),
        findsOneWidget,
      );
      expect(find.text('Done ✓'), findsOneWidget);
      // Only executable options offer Send (unsafe + done do not).
      expect(find.text('Send'), findsNWidgets(3));
      await tester.tap(find.text('Send').first);
      expect(executed, 'opt_defrost');
    });
  });

  group('WatchingCard', () {
    testWidgets('renders the quiet message', (tester) async {
      await _pumpCard(
        tester,
        const WatchingCard(message: 'All quiet — watching 2 systems.'),
      );
      expect(find.textContaining('All quiet'), findsOneWidget);
    });
  });

  group('PauseAllTile', () {
    testWidgets('switch and banner follow the paused state',
        (tester) async {
      bool? changedTo;
      await _pumpCard(
        tester,
        PauseAllTile(paused: false, onChanged: (v) => changedTo = v),
      );
      expect(find.text('Pause all actions'), findsOneWidget);
      expect(find.textContaining('Paused —'), findsNothing);
      await tester.tap(find.byType(Switch));
      expect(changedTo, isTrue);

      await _pumpCard(
        tester,
        PauseAllTile(paused: true, onChanged: (_) {}),
      );
      expect(find.textContaining('Paused —'), findsOneWidget);
    });
  });
}
