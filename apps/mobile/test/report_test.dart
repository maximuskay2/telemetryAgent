import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telemetry_agent/models/pending_action.dart';
import 'package:telemetry_agent/models/run_report.dart';
import 'package:telemetry_agent/providers.dart';
import 'package:telemetry_agent/screens/alarm_screen.dart' show outcomeTitle;
import 'package:telemetry_agent/screens/report_screen.dart';

RunReport _row({String? decision, String status = 'PASS'}) => RunReport(
      runId: 'r',
      domain: 'software',
      status: status,
      decision: decision,
    );

void main() {
  group('ReportFilter', () {
    test('matches decisions and FAIL status', () {
      expect(ReportFilter.all.matches(_row()), isTrue);
      expect(ReportFilter.open.matches(_row(decision: 'pending')), isTrue);
      expect(ReportFilter.open.matches(_row(decision: 'approved')), isFalse);
      expect(
          ReportFilter.autoApplied
              .matches(_row(decision: 'auto_applied')),
          isTrue);
      expect(ReportFilter.approved.matches(_row(decision: 'approved')),
          isTrue);
      expect(
          ReportFilter.disapproved
              .matches(_row(decision: 'disapproved')),
          isTrue);
      expect(ReportFilter.failed.matches(_row(decision: 'failed')), isTrue);
      expect(ReportFilter.failed.matches(_row(status: 'FAIL')), isTrue);
      expect(ReportFilter.failed.matches(_row(decision: 'approved')),
          isFalse);
    });

    test('ignored matches suppressed gate verdicts', () {
      const suppressed = RunReport(
        runId: 'r',
        domain: 'software',
        status: 'NO_ACTION',
        gate: GateDecision(
            decision: 'suppress', reason: 'defrost', citation: 'spec p.2'),
      );
      expect(ReportFilter.ignored.matches(suppressed), isTrue);
      expect(ReportFilter.ignored.matches(_row()), isFalse);
    });
  });

  group('RunReport detail', () {
    test('parses timings, suggestions, and the decision record', () {
      final detail = RunReport.fromDetailJson({
        'run_id': 'r',
        'domain': 'software',
        'result': {'status': 'PASS', 'attempts': 2, 'model_used': 'm'},
        'steps': [
          {
            'step': 'diagnose',
            'model': 'm',
            'detail': 'Lock inversion',
            'duration_ms': 1200,
            'suggestions': ['Check lock order', 'Add test'],
          },
          {'step': 'verify', 'status': 'PASS', 'duration_ms': 800},
        ],
        'decision': {
          'run_id': 'r',
          'domain': 'software',
          'action': 'Deploy the patch',
          'opened_at': 1000,
          'deadline': 1020,
          'state': 'approved',
          'decided_by': 'pixel',
          'resolved_at': 1008,
          'detail': 'applied by pixel',
        },
      });
      expect(detail.pipelineMs, 2000);
      expect(
          detail.steps.first.suggestions,
          ['Check lock order', 'Add test']);
      expect(detail.decisionDetail, isA<PendingAction>());
      expect(detail.decisionDetail!.decidedBy, 'pixel');
    });

    test('reads S1 verification evidence when present', () {
      final detail = RunReport.fromDetailJson({
        'run_id': 'r',
        'domain': 'software',
        'result': {'status': 'PASS'},
        'steps': const [],
        'verification': {
          'runner': 'docker',
          'original': {'passed': false, 'output': '1 failed'},
          'patched': {'passed': true, 'output': '3 passed'},
        },
      });
      expect(detail.verificationRunner, 'docker');
      expect(detail.verifyFailedOnOriginal, isTrue);
      expect(detail.verifyPassedOnPatch, isTrue);
      expect(detail.verifyLine, 'Verified: tests fail→pass in docker');
    });

    test('pre-S1 runs render without verification', () {
      final detail = RunReport.fromDetailJson({
        'run_id': 'r',
        'domain': 'software',
        'result': {'status': 'PASS'},
        'steps': const [],
      });
      expect(detail.verification, isNull);
      expect(detail.verifyLine, isEmpty);
    });
  });

  group('reportSummary', () {
    test('carries diagnosis, decision, and PR', () {
      final detail = RunReport.fromDetailJson({
        'run_id': 'abc123',
        'domain': 'software',
        'result': {
          'status': 'PASS',
          'pr_url': 'https://github.com/x/y/pull/1',
        },
        'steps': [
          {
            'step': 'diagnose',
            'detail': 'Lock inversion\nsecond line',
            'suggestions': ['Check lock order'],
          },
        ],
        'decision': {
          'run_id': 'abc123',
          'domain': 'software',
          'action': 'Deploy',
          'opened_at': 1000,
          'deadline': 1020,
          'state': 'auto_applied',
          'resolved_at': 1020,
        },
      });
      final summary = reportSummary(detail);
      expect(summary, contains('abc123'));
      expect(summary, contains('Diagnosis: Lock inversion'));
      expect(summary, contains('• Check lock order'));
      expect(summary, contains('Auto-applied ✓'));
      expect(summary,
          contains('PR: https://github.com/x/y/pull/1'));
    });
  });

  group('outcomeTitle', () {
    PendingAction actionWith(String state) => PendingAction(
          runId: 'r',
          domain: 'software',
          action: 'Deploy',
          openedAt: 1000,
          deadline: 1020,
          state: state,
        );

    test('covers every decision state', () {
      expect(outcomeTitle(actionWith('pending')), 'Veto window open');
      expect(outcomeTitle(actionWith('approved')), 'Approved ✓');
      expect(outcomeTitle(actionWith('auto_applied')), 'Auto-applied ✓');
      expect(outcomeTitle(actionWith('disapproved')),
          'Disapproved — left for a human');
      expect(outcomeTitle(actionWith('failed')), 'Apply failed');
      expect(outcomeTitle(actionWith('expired')), 'Window expired');
      expect(outcomeTitle(actionWith('pending'), tooLate: true),
          'Too late — already applied');
    });
  });

  group('ReportBody', () {
    testWidgets('software report shows fix, decision, and PR',
        (tester) async {
      tester.view.physicalSize = const Size(800, 4000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      final detail = RunReport.fromDetailJson({
        'run_id': 'run-software-1',
        'domain': 'software',
        'result': {
          'status': 'PASS',
          'attempts': 1,
          'model_used': 'meta-model',
          'patch_code': 'def fixed():\n    return True',
          'pr_url': 'https://github.com/x/y/pull/2',
        },
        'steps': [
          {'step': 'diagnose', 'model': 'meta-model', 'detail': 'Locks'},
          {'step': 'verify', 'status': 'PASS'},
          {'step': 'done', 'status': 'PASS', 'message': 'Verified'},
        ],
        'decision': {
          'run_id': 'run-software-1',
          'domain': 'software',
          'action': 'Deploy the verified inventory patch',
          'opened_at': 1000,
          'deadline': 1020,
          'state': 'auto_applied',
          'resolved_at': 1020,
        },
      });
      var opened = '';
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: ReportBody(
                report: detail,
                onOpenPr: (url) => opened = url,
              ),
            ),
          ),
        ),
      );
      expect(find.text('Auto-applied ✓'), findsOneWidget);
      expect(find.textContaining('def fixed()'), findsOneWidget);
      expect(find.text('Open fix PR'), findsOneWidget);
      await tester.tap(find.text('Open fix PR'));
      expect(opened, 'https://github.com/x/y/pull/2');
    });

    testWidgets('appliance report shows runbook and temp chart slot',
        (tester) async {
      tester.view.physicalSize = const Size(800, 4000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      final detail = RunReport.fromDetailJson({
        'run_id': 'run-fridge-1',
        'domain': 'appliance',
        'result': {
          'status': 'PASS',
          'runbook': {
            'steps': ['Close the door', 'Clean the condenser'],
            'target_temperature_c': 4.0,
            'restart_delay_s': 180,
            'power_off_minutes': 0,
            'disables_protection': false,
          },
          'alert': {'work_order_id': 'WO-7', 'message': 'Fridge warm'},
        },
        'steps': [
          {'step': 'diagnose', 'detail': 'Door left open'},
        ],
        'decision': null,
      });
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: ReportBody(
                report: detail,
                onOpenPr: (_) {},
              ),
            ),
          ),
        ),
      );
      expect(find.textContaining('Close the door'), findsOneWidget);
      expect(find.textContaining('WO-7'), findsOneWidget);
      expect(
          find.textContaining('Collecting live readings'),
          findsOneWidget);
    });
  });

  group('gate decision', () {
    test('parses verdict, reason, citation, and checks', () {
      final detail = RunReport.fromDetailJson({
        'run_id': 'r',
        'domain': 'appliance',
        'result': {'status': 'PASS'},
        'steps': [],
        'gate': {
          'decision': 'act',
          'reason': 'Hot cabinet: temp_c 7.5 > 5.5 for 1500s',
          'citation': 'coldchain_spec_sheet.pdf p.2',
          'checks': [
            {'name': 'hard_limit', 'result': 'pass', 'detail': 'no breach'},
            {'name': 'impact', 'result': 'trigger', 'detail': 'hot cabinet'},
          ],
        },
      });
      final gate = detail.gate!;
      expect(gate.decision, 'act');
      expect(gate.label, 'Escalated');
      expect(gate.reason, contains('Hot cabinet'));
      expect(gate.citation, contains('coldchain_spec_sheet.pdf'));
      expect(gate.checks, hasLength(2));
      expect(gate.checks.last.name, 'impact');
    });

    test('labels suppress and observe verdicts', () {
      expect(
          const GateDecision(decision: 'suppress', reason: '', citation: '')
              .label,
          'Suppressed');
      expect(
          const GateDecision(decision: 'observe', reason: '', citation: '')
              .label,
          'Watching');
    });

    test('list rows carry the verdict without detail', () {
      final row = RunReport.fromListJson({
        'run_id': 'r',
        'domain': 'software',
        'status': 'PASS',
        'gate_decision': 'suppress',
      });
      expect(row.gate!.decision, 'suppress');
      expect(row.gate!.label, 'Suppressed');
      final plain = RunReport.fromListJson({
        'run_id': 'r2',
        'domain': 'software',
        'status': 'PASS',
      });
      expect(plain.gate, isNull);
    });

    testWidgets('gate card shows reason and citation', (tester) async {
      tester.view.physicalSize = const Size(800, 4000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      final detail = RunReport.fromDetailJson({
        'run_id': 'r',
        'domain': 'appliance',
        'result': {'status': 'PASS'},
        'steps': [],
        'gate': {
          'decision': 'suppress',
          'reason': 'Mode defrost explains it',
          'citation': 'coldchain_spec_sheet.pdf p.1',
          'checks': [],
        },
      });
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: ReportBody(
                report: RunReport(
                  runId: 'r',
                  domain: 'appliance',
                  status: 'PASS',
                  gate: GateDecision(
                    decision: 'suppress',
                    reason: 'Mode defrost explains it',
                    citation: 'coldchain_spec_sheet.pdf p.1',
                  ),
                ),
                onOpenPr: (_) {},
              ),
            ),
          ),
        ),
      );
      expect(detail.gate!.label, 'Suppressed');
      expect(find.text('GATE: SUPPRESSED'), findsOneWidget);
      expect(find.textContaining('Mode defrost explains it'),
          findsOneWidget);
      expect(find.textContaining('coldchain_spec_sheet.pdf p.1'),
          findsOneWidget);
    });
  });
}
