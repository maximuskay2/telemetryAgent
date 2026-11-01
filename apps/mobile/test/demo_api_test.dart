import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:telemetry_agent/models/connection.dart';
import 'package:telemetry_agent/services/api.dart';

AgentApi _api(Connection connection,
    Future<http.Response> Function(http.Request) handler) {
  return AgentApi(connection: connection, client: MockClient(handler));
}

const _demo = Connection(
  apiUrl: 'http://localhost:8201',
  token: 'ta_demo_abc',
  deviceName: 'phone',
);

void main() {
  group('demo device session', () {
    test('registerDemoDevice posts the label, parses the token', () async {
      final api = _api(
        const Connection(
            apiUrl: 'http://localhost:8201', token: '', deviceName: ''),
        (request) async {
          expect(request.url.path, '/api/demo/devices');
          expect(request.headers['Authorization'], isNull);
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['label'], 'phone');
          return http.Response(
            jsonEncode(
                {'device_id': 'dd1', 'device_token': 'ta_demo_abc'}),
            200,
          );
        },
      );
      final registered = await api.registerDemoDevice('phone');
      expect(registered.deviceId, 'dd1');
      expect(registered.deviceToken, 'ta_demo_abc');
    });

    test('declareWatch puts systems with the demo bearer', () async {
      final api = _api(_demo, (request) async {
        expect(request.url.path, '/api/demo/devices/watch');
        expect(request.method, 'PUT');
        expect(request.headers['Authorization'], 'Bearer ta_demo_abc');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['systems'], ['shop', 'freezer']);
        return http.Response(
            jsonEncode({'device_id': 'dd1'}), 200);
      });
      await api.declareWatch(['shop', 'freezer']);
    });

    test('decide rides Authorization Bearer on demo sessions', () async {
      final api = _api(_demo, (request) async {
        expect(request.url.path, '/api/actions/r1/approve');
        expect(request.headers['Authorization'], 'Bearer ta_demo_abc');
        expect(request.headers['X-Mobile-Token'], isNull);
        return http.Response(
          jsonEncode({
            'run_id': 'r1',
            'domain': 'software',
            'action': 'x',
            'opened_at': 1,
            'deadline': 2,
            'state': 'approved',
          }),
          200,
        );
      });
      final action = await api.decide('r1', true);
      expect(action.state, 'approved');
    });

    test('wsUri identifies device sockets, legacy stays anonymous', () {
      const legacy = Connection(
          apiUrl: 'http://host:8001', token: 'secret', deviceName: 'p');
      expect(legacy.wsUri.toString(), 'ws://host:8001/api/ws');

      expect(_demo.wsUri.queryParameters['token'], 'ta_demo_abc');
      expect(_demo.wsUri.queryParameters.containsKey('org'), isFalse);

      const claimed = Connection(
        apiUrl: 'https://host',
        token: 'ta_dev_xyz',
        deviceName: 'p',
        orgId: 'o1',
      );
      expect(claimed.wsUri.queryParameters['token'], 'ta_dev_xyz');
      expect(claimed.wsUri.queryParameters['org'], 'o1');
      expect(claimed.wsUri.queryParameters['demo'], '1');
    });
  });
}
