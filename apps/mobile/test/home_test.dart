import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telemetry_agent/models/run_report.dart';
import 'package:telemetry_agent/providers.dart';
import 'package:telemetry_agent/screens/home_screen.dart';
import 'package:telemetry_agent/screens/report_screen.dart';
import 'package:telemetry_agent/services/api.dart';

const _demo = SystemSummary(
  systemId: 'sys-demo',
  name: 'AutoParts Lagos',
  kind: 'software',
  status: 'armed',
);
const _prod = SystemSummary(
  systemId: 'sys-prod',
  name: 'Shop API',
  kind: 'software',
  status: 'armed',
);

RunReport _row({String systemId = '', String status = 'PASS'}) => RunReport(
      runId: 'run-1',
      domain: 'software',
      status: status,
      gate: systemId.isEmpty
          ? null
          : GateDecision(
              decision: 'act',
              reason: 'r',
              citation: 'c',
              systemId: systemId,
            ),
    );

Future<void> _pumpRow(
  WidgetTester tester,
  RunReport report,
  List<SystemSummary> systems,
) async {
  tester.view.physicalSize = const Size(800, 1200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        systemsProvider.overrideWith((ref) => Future.value(systems)),
      ],
      child: MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: RunRow(report: report))),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('systemLabelFor', () {
    test('prefers the run\'s own system over a same-kind demo', () {
      expect(
        systemLabelFor(_row(systemId: 'sys-prod'), [_demo, _prod]),
        'Shop API',
      );
    });

    test('falls back to the kind match without a system id', () {
      expect(systemLabelFor(_row(), [_demo, _prod]), 'AutoParts Lagos');
    });

    test('falls back to the domain without any system', () {
      expect(systemLabelFor(_row(), []), 'software');
    });

    test('fromListJson parses the runs-list system_id', () {
      final row = RunReport.fromListJson({
        'run_id': 'r',
        'domain': 'software',
        'status': 'PASS',
        'gate_decision': 'act',
        'system_id': 'sys-prod',
      });
      expect(row.gate?.systemId, 'sys-prod');
      expect(systemLabelFor(row, [_demo, _prod]), 'Shop API');
    });
  });

  group('RunRow', () {
    testWidgets('labels a production run with its own system', (tester) async {
      await _pumpRow(tester, _row(systemId: 'sys-prod'), [_demo, _prod]);
      expect(find.textContaining('Shop API'), findsOneWidget);
      expect(find.textContaining('AutoParts'), findsNothing);
    });

    testWidgets('keeps the kind match for legacy rows', (tester) async {
      await _pumpRow(tester, _row(), [_demo, _prod]);
      expect(find.textContaining('AutoParts Lagos'), findsOneWidget);
    });
  });

  group('Decision record without a veto window', () {
    Future<void> pumpBody(WidgetTester tester, RunReport report) async {
      tester.view.physicalSize = const Size(800, 4000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: ReportBody(report: report, onOpenPr: (_) {}),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('PASS says the fix needed no veto', (tester) async {
      await pumpBody(tester, _row(status: 'PASS'));
      expect(
        find.text('Passed — the verified fix needed no veto.'),
        findsOneWidget,
      );
      expect(find.textContaining('FAIL runs'), findsNothing);
    });

    testWidgets('NO_ACTION says nothing was proposed', (tester) async {
      await pumpBody(tester, _row(status: 'NO_ACTION'));
      expect(
        find.text('No action was proposed — nothing to veto.'),
        findsOneWidget,
      );
    });

    testWidgets('FAIL keeps the veto-window explainer', (tester) async {
      await pumpBody(tester, _row(status: 'FAIL'));
      expect(
        find.text(
          'No veto window — FAIL runs and unsafe runbooks never auto-apply.',
        ),
        findsOneWidget,
      );
    });
  });
}
