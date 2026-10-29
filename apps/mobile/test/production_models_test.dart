import 'package:flutter_test/flutter_test.dart';
import 'package:telemetry_agent/models/production.dart';

/// §3.4 fixture scalars (same values as core/schemas/production.py).
const _connection = {
  'id': 'con_ab12',
  'system_id': 'acme-api-9f2c',
  'kind': 'logs',
  'config': {'service': 'api'},
  'secret_hint': '****abcd',
  'status': 'waiting',
  'detail': '',
  'last_seen': 1730200000.0,
};

const _option = {
  'id': 'opt_1',
  'kind': 'open_pr',
  'title': 'Open fix PR',
  'detail': 'Verified fix: reproduce test fails, patch passes, suite green',
  'url': 'https://github.com/acme/api/pull/7',
  'safety': {'ok': true, 'reason': ''},
  'status': 'available',
};

const _command = {
  'id': 'cmd_1',
  'action': 'defrost',
  'params': {},
  'expires_at': 1730200120.0,
};

void main() {
  group('§3.4 mirrors', () {
    test('ProdConnection parses the fixture', () {
      final connection = ProdConnection.fromJson(_connection);
      expect(connection.id, 'con_ab12');
      expect(connection.systemId, 'acme-api-9f2c');
      expect(connection.kind, 'logs');
      expect(connection.config, {'service': 'api'});
      expect(connection.secretHint, '****abcd');
      expect(connection.status, 'waiting');
      expect(connection.lastSeen, 1730200000.0);
    });

    test('ConnectionTestResult parses permissions', () {
      final result = ConnectionTestResult.fromJson({
        'ok': true,
        'detail': 'stub: reachable',
        'permissions': {'read': true, 'pull_requests': true},
      });
      expect(result.ok, isTrue);
      expect(result.hasPermissions, isTrue);
      expect(result.canRead, isTrue);
      expect(result.canOpenPrs, isTrue);
      final bare =
          ConnectionTestResult.fromJson({'ok': false, 'detail': 'no'});
      expect(bare.hasPermissions, isFalse);
    });

    test('ProdOption parses the fixture', () {
      final option = ProdOption.fromJson(_option);
      expect(option.id, 'opt_1');
      expect(option.kind, 'open_pr');
      expect(option.title, 'Open fix PR');
      expect(option.url, 'https://github.com/acme/api/pull/7');
      expect(option.safety.ok, isTrue);
      expect(option.status, 'available');
      expect(option.executable, isTrue);
    });

    test('unsafe options are not executable', () {
      final option = ProdOption.fromJson({
        'id': 'opt_x',
        'kind': 'remote',
        'title': 'Power-cycle compressor',
        'safety': {'ok': false, 'reason': 'wait 170s more'},
        'status': 'available',
      });
      expect(option.executable, isFalse);
      expect(option.safety.reason, 'wait 170s more');
    });

    test('IncidentOptions parses the list envelope', () {
      final result = IncidentOptions.fromJson({
        'run_id': 'run9',
        'domain': 'software',
        'options': [_option],
      });
      expect(result.runId, 'run9');
      expect(result.domain, 'software');
      expect(result.options, hasLength(1));
      expect(result.options.first.id, 'opt_1');
    });

    test('DeviceCommandItem parses the fixture', () {
      final command = DeviceCommandItem.fromJson(_command);
      expect(command.id, 'cmd_1');
      expect(command.action, 'defrost');
      expect(command.params, isEmpty);
      expect(command.expiresAt, 1730200120.0);
    });

    test('PauseState and suite summaries parse', () {
      expect(PauseState.fromJson({'paused': true}).paused, isTrue);
      final suite = SuiteSummary.fromJson(
          {'passed': 212, 'failed': 0, 'new_failures': 0});
      expect(suite.passed, 212);
      expect(suite.green, isTrue);
      final red =
          SuiteSummary.fromJson({'passed': 1, 'failed': 0, 'new_failures': 2});
      expect(red.green, isFalse);
    });

    test('SoftwareRunResult parses pr, suite, and mitigation', () {
      final result = SoftwareRunResult.fromJson({
        'pr_url': 'https://github.com/acme/api/pull/7',
        'repo': 'acme/api',
        'suite': {'passed': 212, 'failed': 0, 'new_failures': 0},
        'mitigation': {'action': 'rollback', 'status': 'proposed'},
      });
      expect(result.prUrl, contains('/pull/7'));
      expect(result.repo, 'acme/api');
      expect(result.suite!.green, isTrue);
      expect(result.mitigation!.action, 'rollback');
      final empty = SoftwareRunResult.fromJson({});
      expect(empty.prUrl, isEmpty);
      expect(empty.suite, isNull);
    });
  });
}
