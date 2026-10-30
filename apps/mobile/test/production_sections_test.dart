import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:telemetry_agent/models/connection.dart';
import 'package:telemetry_agent/models/pending_action.dart';
import 'package:telemetry_agent/models/production.dart';
import 'package:telemetry_agent/models/run_report.dart';
import 'package:telemetry_agent/models/sim_event.dart';
import 'package:telemetry_agent/providers.dart';
import 'package:telemetry_agent/services/api.dart';
import 'package:telemetry_agent/widgets/production_sections.dart';

const _connection = Connection(
  apiUrl: 'http://localhost:8201',
  token: 'test-token',
  deviceName: 'test',
);

AgentApi _mockApi(Future<http.Response> Function(http.Request) handler) {
  return AgentApi(connection: _connection, client: MockClient(handler));
}

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  AgentApi? api,
  IncidentOptions? options,
  List<PendingAction>? open,
  bool settle = true,
}) async {
  tester.view.physicalSize = const Size(800, 4000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    // The overrides literal stays inline: Override is internal in
    // Riverpod 3, so the type cannot be named in a helper signature.
    ProviderScope(
      overrides: [
        if (api != null) apiProvider.overrideWithValue(api),
        if (options != null)
          incidentOptionsProvider('run-1')
              .overrideWith((ref) => Future.value(options)),
        if (open != null)
          openActionsProvider.overrideWith((ref) => Future.value(open)),
      ],
      child: MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: child)),
      ),
    ),
  );
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    // Screens with a live countdown never settle; flush async work
    // with bounded pumps instead.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));
  }
}

RunReport _report(String domain) => RunReport.fromDetailJson({
      'run_id': 'run-1',
      'domain': domain,
      'result': {
        'status': 'PASS',
        'pr_url': 'https://github.com/acme/api/pull/7',
        'suite': {'passed': 212, 'failed': 0, 'new_failures': 0},
      },
      'steps': [
        {'step': 'diagnose', 'detail': 'Empty-cart total divides by zero'},
      ],
    });

const _hardwareOptions = IncidentOptions(
  runId: 'run-1',
  domain: 'appliance',
  options: [
    ProdOption(
        id: 'opt_defrost',
        kind: 'remote',
        title: 'Start defrost',
        detail: 'Run the defrost cycle now.'),
    ProdOption(
      id: 'opt_setpoint',
      kind: 'remote',
      title: 'Lower setpoint 1 °C',
      safety: OptionSafety(ok: false, reason: 'wait 170s more'),
    ),
    ProdOption(id: 'opt_door', kind: 'manual', title: 'Close the door'),
  ],
);

void main() {
  group('HardwareOptionsSection', () {
    testWidgets('live options with working Send', (tester) async {
      final calls = <String>[];
      final api = _mockApi((request) async {
        calls.add('${request.method} ${request.url.path}');
        return http.Response(
            jsonEncode({'status': 'sent', 'command_id': 'cmd_1'}), 200);
      });
      await _pump(
        tester,
        HardwareOptionsSection(report: _report('appliance')),
        api: api,
        options: _hardwareOptions,
      );
      expect(find.text('Start defrost'), findsOneWidget);
      expect(find.text('Disabled: wait 170s more'), findsOneWidget);
      expect(find.text('Send'), findsNWidgets(2));
      await tester.tap(find.text('Send').first);
      await tester.pumpAndSettle();
      expect(
        calls,
        contains('POST /api/incidents/run-1/options/opt_defrost/execute'),
      );
    });
  });

  group('SoftwarePrSection', () {
    testWidgets('PR card with mitigation countdown', (tester) async {
      final calls = <String>[];
      final api = _mockApi((request) async {
        calls.add('${request.method} ${request.url.path}');
        return http.Response(
            jsonEncode({'status': 'sent', 'command_id': ''}), 200);
      });
      final action = PendingAction(
        runId: 'run-1',
        domain: 'software',
        action: 'Roll back to previous deploy',
        openedAt: 1000,
        deadline: DateTime.now().millisecondsSinceEpoch / 1000 + 14,
      );
      await _pump(
        tester,
        SoftwarePrSection(report: _report('software'), onOpenPr: (_) {}),
        api: api,
        options: const IncidentOptions(
          runId: 'run-1',
          domain: 'software',
          options: [
            ProdOption(
              id: 'opt_rollback',
              kind: 'rollback',
              title: 'Roll back to previous deploy',
              url: 'https://github.com/acme/api/pull/7',
            ),
          ],
        ),
        open: [action],
        settle: false,
      );
      expect(find.textContaining('divides by zero'), findsOneWidget);
      expect(find.textContaining('suite green'), findsOneWidget);
      expect(find.text('Open PR'), findsOneWidget);
      expect(find.text('Roll back now'), findsOneWidget);
      expect(find.textContaining('14s'), findsOneWidget);
      await tester.tap(find.text('Roll back now'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(
        calls,
        contains('POST /api/incidents/run-1/options/opt_rollback/execute'),
      );
    });

    testWidgets('pending states without options', (tester) async {
      final api = _mockApi((request) async {
        return http.Response(
          jsonEncode(
              {'run_id': 'run-1', 'domain': 'software', 'options': []}),
          200,
          request: request,
        );
      });
      await _pump(
        tester,
        SoftwarePrSection(report: _report('software'), onOpenPr: (_) {}),
        api: api,
        options: const IncidentOptions(
            runId: 'run-1', domain: 'software', options: []),
      );
      expect(find.text('No mitigation proposed.'), findsOneWidget);
    });
  });

  group('PauseSection', () {
    testWidgets('switch flips the server state', (tester) async {
      var paused = false;
      final api = _mockApi((request) async {
        if (request.method == 'POST') {
          paused = (jsonDecode(request.body)
              as Map<String, dynamic>)['paused'] as bool;
        }
        return http.Response(jsonEncode({'paused': paused}), 200);
      });
      await _pump(
        tester,
        const PauseSection(),
        api: api,
      );
      expect(find.text('Pause all actions'), findsOneWidget);
      expect(find.textContaining('Paused —'), findsNothing);
      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();
      expect(paused, isTrue);
      expect(find.textContaining('Paused —'), findsOneWidget);
    });

    test('applyRemote follows actions_paused events', () async {
      final api = _mockApi((_) async =>
          http.Response(jsonEncode({'paused': false}), 200));
      final container = ProviderContainer(
        overrides: [apiProvider.overrideWithValue(api)],
      );
      addTearDown(container.dispose);
      expect(await container.read(pauseProvider.future), isFalse);
      container.read(pauseProvider.notifier).applyRemote(true);
      expect(container.read(pauseProvider).asData?.value, isTrue);
    });
  });

  group('production event sentences', () {
    test('feed lines for the new kinds', () {
      expect(
        const SimEvent(
          kind: 'pr_opened',
          payload: {'pr_url': 'https://github.com/a/b/pull/7'},
        ).sentence(),
        contains('/pull/7'),
      );
      expect(
        const SimEvent(
          kind: 'connection_status',
          payload: {'system_id': 'shop', 'status': 'ok'},
        ).sentence(),
        contains('Connected'),
      );
      expect(
        const SimEvent(
          kind: 'actions_paused',
          payload: {'paused': true},
        ).sentence(),
        contains('paused'),
      );
      expect(
        const SimEvent(kind: 'option_status', payload: {}).sentence(),
        isNull,
      );
    });
  });
}
