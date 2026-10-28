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
          find.textContaining('Collecting live temperatures'),
          findsOneWidget);
    });
  });
}
