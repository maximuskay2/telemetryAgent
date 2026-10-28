import 'package:flutter_test/flutter_test.dart';
import 'package:telemetry_agent/models/agent_step.dart';
import 'package:telemetry_agent/models/connection.dart';
import 'package:telemetry_agent/models/pending_action.dart';
import 'package:telemetry_agent/models/run_report.dart';
import 'package:telemetry_agent/models/sim_event.dart';
import 'package:telemetry_agent/screens/scan_screen.dart';
import 'package:telemetry_agent/services/socket.dart';

void main() {
  group('Connection', () {
    test('wsUri upgrades http/https', () {
      const http = Connection(apiUrl: 'http://host:8001', token: '', deviceName: 'p');
      const https = Connection(apiUrl: 'https://host', token: '', deviceName: 'p');
      expect(http.wsUri.toString(), 'ws://host:8001/api/ws');
      expect(https.wsUri.toString(), 'wss://host/api/ws');
    });
  });

  group('AgentStep', () {
    test('milestone sentences mirror the dashboard', () {
      expect(
        AgentStep.fromJson({
          'step': 'diagnose',
          'model': 'm',
          'detail': 'Lock ordering inversion\nmore',
        }).sentence(),
        'Diagnosed: Lock ordering inversion',
      );
      expect(
        AgentStep.fromJson({'step': 'generate', 'attempt': 2}).sentence(),
        'Wrote a fix (attempt 2)',
      );
      expect(
        AgentStep.fromJson({'step': 'verify', 'status': 'PASS'}).sentence(),
        'Sandbox verification: PASS',
      );
      expect(
        AgentStep.fromJson({'step': 'done', 'status': 'PASS'}).sentence(),
        'Run finished: verified fix',
      );
    });
  });

  group('SimEvent', () {
    test('watcher and fix sentences', () {
      expect(
        SimEvent.fromJson({
          'kind': 'watcher_trigger',
          'payload': {'rule': 'retry-cluster', 'resource': 'axle,gasket'},
        }).sentence(),
        'Watcher caught a retry storm on axle,gasket',
      );
      expect(
        SimEvent.fromJson({
          'kind': 'fix_applied',
          'payload': {'domain': 'software'},
        }).sentence(),
        'Fix applied to shop (merge and deploy)',
      );
      expect(
        SimEvent.fromJson({
          'kind': 'action_resolved',
          'payload': {'state': 'disapproved', 'decided_by': 'pixel'},
        }).sentence(),
        'Action disapproved by pixel',
      );
    });

    test('visual-only events stay out of the feed', () {
      expect(SimEvent.fromJson({'kind': 'shop_order'}).sentence(), isNull);
      expect(SimEvent.fromJson({'kind': 'fridge_reading'}).sentence(), isNull);
      expect(SimEvent.fromJson({'kind': 'shop_metrics'}).sentence(), isNull);
    });
  });

  group('PendingAction', () {
    test('secondsLeft counts down from the deadline', () {
      final action = PendingAction(
        runId: 'r',
        domain: 'software',
        action: 'Deploy',
        openedAt: 1000,
        deadline: 1020,
      );
      final at = DateTime.fromMillisecondsSinceEpoch(1005 * 1000);
      expect(action.secondsLeft(at), 15);
      final late = DateTime.fromMillisecondsSinceEpoch(1030 * 1000);
      expect(action.secondsLeft(late), 0);
    });
  });

  group('RunReport', () {
    test('list and detail shapes parse', () {
      final row = RunReport.fromListJson({
        'run_id': 'r',
        'domain': 'software',
        'status': 'PASS',
        'attempts': 2,
        'model_used': 'm',
        'source': 'watcher',
        'n_steps': 4,
        'decision': 'pending',
      });
      expect(row.decision, 'pending');
      final detail = RunReport.fromDetailJson({
        'run_id': 'r',
        'domain': 'software',
        'result': {'status': 'PASS'},
        'steps': [
          {'step': 'diagnose', 'model': 'm'},
        ],
        'decision': {'state': 'auto_applied'},
      });
      expect(detail.steps, hasLength(1));
      expect(detail.decision, 'auto_applied');
    });
  });

  group('FeedItem.parse', () {
    test('routes steps, events, and log lines', () {
      expect(
        FeedItem.parse({'step': 'generate', 'attempt': 1, 'domain': 'software'})
            ?.message,
        'Wrote a fix (attempt 1)',
      );
      expect(
        FeedItem.parse({
          'kind': 'watcher_trigger',
          'payload': {'rule': 'deadlock'},
        })?.source,
        'watcher',
      );
      expect(
        FeedItem.parse({'message': 'hi', 'source': 'shop', 'level': 'ERROR'})
            ?.level,
        'ERROR',
      );
      expect(FeedItem.parse({'kind': 'shop_order'}), isNull);
      expect(FeedItem.parse('not json'), isNull);
    });
  });

  group('parsePairingCode', () {
    test('accepts raw URLs and dashboard JSON', () {
      expect(parsePairingCode('http://a:8001'), 'http://a:8001');
      expect(parsePairingCode('{"api": "http://a:8001"}'), 'http://a:8001');
      expect(parsePairingCode('hello'), isNull);
      expect(parsePairingCode(null), isNull);
      expect(parsePairingCode('{"nope": 1}'), isNull);
    });
  });
}
