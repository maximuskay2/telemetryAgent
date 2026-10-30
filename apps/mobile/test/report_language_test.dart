import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telemetry_agent/models/run_report.dart';
import 'package:telemetry_agent/screens/report_screen.dart';

// L-N4: the report shows the incident language + test runner, and
// "auto-fix not supported" incidents read clearly.

Future<void> _pumpReport(WidgetTester tester, RunReport report) {
  return tester.pumpWidget(
    ProviderScope(
      child: MaterialApp(
        home: Scaffold(
          body: ReportBody(
            report: report,
            onOpenPr: (_) {},
          ),
        ),
      ),
    ),
  );
}

void main() {
  group('RunReport language', () {
    test('parses the gate language', () {
      final detail = RunReport.fromDetailJson({
        'run_id': 'r',
        'result': {'status': 'PASS'},
        'gate': {
          'decision': 'act',
          'reason': 'fix it',
          'citation': '',
          'language': 'typescript',
        },
      });
      expect(detail.language, 'typescript');
      expect(languageLabel('typescript'), 'TypeScript');
    });

    test('falls back to result language, then empty', () {
      final fromResult = RunReport.fromDetailJson({
        'run_id': 'r',
        'result': {'status': 'PASS', 'language': 'go'},
      });
      expect(fromResult.language, 'go');
      final absent = RunReport.fromDetailJson({
        'run_id': 'r',
        'result': {'status': 'PASS'},
      });
      expect(absent.language, '');
    });

    test('labels every adapter language, passes others through', () {
      expect(languageLabel('python'), 'Python');
      expect(languageLabel('javascript'), 'JavaScript');
      expect(languageLabel('java'), 'Java');
      expect(languageLabel('kotlin'), 'Kotlin');
      expect(languageLabel('go'), 'Go');
      expect(languageLabel('rust'), 'Rust');
      expect(languageLabel('php'), 'PHP');
      expect(languageLabel('c#'), 'c#');
    });
  });

  group('ReportBody language', () {
    testWidgets('supported run shows the language and runner',
        (tester) async {
      // Gate map captured live: proof-app-node trigger.sh output through
      // the real ingest pipeline (L-J2), 30 Oct (synthetic system id).
      final detail = RunReport.fromDetailJson({
        'run_id': 'run-js-1',
        'result': {'status': 'PASS'},
        'gate': {
          'decision': 'observe',
          'reason': 'No impact yet — watching',
          'citation': '',
          'checks': [
            {'name': 'hard_limit', 'result': 'pass', 'detail': 'no breach'},
            {'name': 'armed', 'result': 'pass', 'detail': 'armed'},
            {
              'name': 'expected',
              'result': 'pass',
              'detail': 'no behaviour matched'
            },
            {'name': 'mode', 'result': 'skip', 'detail': 'no mode'},
            {'name': 'baseline', 'result': 'skip', 'detail': 'baseline none'},
            {'name': 'impact', 'result': 'pass', 'detail': 'no impact yet'},
          ],
          'system_id': 'acme-node',
          'language': 'javascript',
        },
        'verification': {
          'runner': 'vitest',
          'original': {'passed': false},
          'patched': {'passed': true},
        },
        'steps': [],
      });
      await _pumpReport(tester, detail);
      expect(find.text('JAVASCRIPT'), findsOneWidget);
      expect(find.text('GATE: WATCHING'), findsOneWidget);
      expect(find.text('No impact yet — watching'), findsOneWidget);
      expect(find.text('AUTO-FIX UNAVAILABLE'), findsNothing);
      expect(find.text('Verified: tests fail→pass in vitest'),
          findsOneWidget);
    });

    testWidgets('unsupported language reads clearly', (tester) async {
      final detail = RunReport.fromDetailJson({
        'run_id': 'run-cs-1',
        'result': {'status': 'NO_ACTION'},
        'gate': {
          'decision': 'suppress',
          'reason': 'auto-fix not supported for c# yet',
          'citation': '',
          'language': 'c#',
        },
        'steps': [],
      });
      await _pumpReport(tester, detail);
      expect(find.text('C#'), findsOneWidget);
      expect(find.text('AUTO-FIX UNAVAILABLE'), findsOneWidget);
      expect(find.text('auto-fix not supported for c# yet'),
          findsOneWidget);
    });

    testWidgets('pre-language runs show no language badge',
        (tester) async {
      const detail = RunReport(
        runId: 'run-old-1',
        domain: 'software',
        status: 'PASS',
      );
      await _pumpReport(tester, detail);
      expect(find.text('AUTO-FIX UNAVAILABLE'), findsNothing);
    });
  });
}
