import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:telemetry_agent/models/connection.dart';
import 'package:telemetry_agent/services/api.dart';

AgentApi _api(Future<http.Response> Function(http.Request) handler) {
  return AgentApi(
    connection: const Connection(
      apiUrl: 'http://localhost:8201',
      token: 'test-token',
      deviceName: 'test',
    ),
    client: MockClient(handler),
  );
}

void main() {
  group('production API', () {
    test('incidentOptions parses the envelope', () async {
      final api = _api((request) async {
        expect(request.url.path, '/api/incidents/run9/options');
        expect(request.headers['X-Mobile-Token'], 'test-token');
        return http.Response(
          jsonEncode({
            'run_id': 'run9',
            'domain': 'appliance',
            'options': [
              {
                'id': 'opt_defrost',
                'kind': 'remote',
                'title': 'Start defrost',
                'safety': {'ok': true, 'reason': ''},
                'status': 'available',
              },
            ],
          }),
          200,
        );
      });
      final result = await api.incidentOptions('run9');
      expect(result.runId, 'run9');
      expect(result.domain, 'appliance');
      expect(result.options, hasLength(1));
      expect(result.options.first.executable, isTrue);
    });

    test('executeOption returns status and command id', () async {
      final api = _api((request) async {
        expect(request.url.path,
            '/api/incidents/run9/options/opt_defrost/execute');
        return http.Response(
          jsonEncode({'status': 'sent', 'command_id': 'cmd_1'}),
          200,
        );
      });
      final result = await api.executeOption('run9', 'opt_defrost');
      expect(result.status, 'sent');
      expect(result.commandId, 'cmd_1');
    });

    test('executeOption surfaces the 409 safety reason', () async {
      final api = _api((_) async => http.Response(
            jsonEncode({'detail': 'wait 170s more (restart delay 180s)'}),
            409,
          ));
      expect(
        () => api.executeOption('run9', 'opt_power_cycle'),
        throwsA(predicate((e) =>
            e is ApiError && e.message.contains('wait 170s'))),
      );
    });

    test('executeOption maps 404 to gone', () async {
      final api =
          _api((_) async => http.Response('{"detail":"x"}', 404));
      expect(
        () => api.executeOption('run9', 'opt_nope'),
        throwsA(predicate(
            (e) => e is ApiError && e.message.contains('gone'))),
      );
    });

    test('pause round-trips', () async {
      var paused = false;
      final api = _api((request) async {
        expect(request.url.path, '/api/actions/pause');
        if (request.method == 'POST') {
          paused = (jsonDecode(request.body)
              as Map<String, dynamic>)['paused'] as bool;
        }
        return http.Response(jsonEncode({'paused': paused}), 200);
      });
      expect(await api.getPaused(), isFalse);
      expect(await api.setPaused(true), isTrue);
      expect(await api.getPaused(), isTrue);
    });
  });
}
