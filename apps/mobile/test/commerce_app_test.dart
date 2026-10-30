import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:telemetry_agent/models/connection.dart';
import 'package:telemetry_agent/models/pending_action.dart';
import 'package:telemetry_agent/providers.dart';
import 'package:telemetry_agent/screens/alarm_screen.dart';
import 'package:telemetry_agent/screens/connect_screen.dart';
import 'package:telemetry_agent/services/api.dart';
import 'package:telemetry_agent/services/storage.dart';

// C-N4: per-user device tokens (§8.4) — claim sign-in, Bearer auth,
// revoked-token re-pair. No network (MockClient + fake keystore).

class FakeSecureStorage extends FlutterSecureStorage {
  final values = <String, String>{};

  @override
  Future<void> write({
    required String key,
    required String? value,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }

  @override
  Future<Map<String, String>> readAll({
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async =>
      Map.of(values);

  @override
  Future<void> deleteAll({
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async =>
      values.clear();
}

AgentApi _api(
  Connection connection,
  Future<http.Response> Function(http.Request) handler,
) =>
    AgentApi(connection: connection, client: MockClient(handler));

const _device = Connection(
  apiUrl: 'http://api:8201',
  token: 'ta_dev_abc',
  deviceName: 'pixel',
  orgId: 'org_acme',
);

const _legacy = Connection(
  apiUrl: 'http://api:8201',
  token: 'shared-secret',
  deviceName: 'phone',
);

void main() {
  group('device auth headers', () {
    test('device tokens ride Authorization Bearer', () async {
      final api = _api(_device, (request) async {
        expect(request.headers['Authorization'], 'Bearer ta_dev_abc');
        expect(request.headers.containsKey('X-Mobile-Token'), false);
        return http.Response('{}', 200);
      });
      await api.checkHealth();
    });

    test('legacy tokens keep X-Mobile-Token', () async {
      final api = _api(_legacy, (request) async {
        expect(request.headers['X-Mobile-Token'], 'shared-secret');
        expect(request.headers.containsKey('Authorization'), false);
        return http.Response('{}', 200);
      });
      await api.checkHealth();
    });
  });

  group('claim', () {
    test('posts the code and parses token + org', () async {
      final api = _api(
        const Connection(apiUrl: 'http://api:8201', token: '', deviceName: ''),
        (request) async {
          expect(request.url.path, '/api/devices/claim');
          expect(request.headers.containsKey('Authorization'), false);
          expect(jsonDecode(request.body)['code'], '123-456');
          return http.Response(
              jsonEncode(
                  {'device_token': 'ta_dev_new', 'org_id': 'org_acme'}),
              200);
        },
      );
      final claimed = await api.claim('123-456');
      expect(claimed.deviceToken, 'ta_dev_new');
      expect(claimed.orgId, 'org_acme');
    });

    test('bad code raises a friendly error', () async {
      final api = _api(_legacy, (request) async => http.Response('{}', 400));
      await expectLater(
        api.claim('nope'),
        throwsA(isA<ApiError>().having(
            (e) => e.message, 'message', contains('didn’t work'))),
      );
    });
  });

  group('revoked tokens', () {
    test('401 marks unauthorized on decide', () async {
      final api = _api(_device, (request) async => http.Response('{}', 401));
      try {
        await api.decide('run1', true);
        fail('expected ApiError');
      } on ApiError catch (error) {
        expect(error.unauthorized, true);
        expect(error.message, contains('re-pair'));
      }
    });

    test('401 marks unauthorized on reads', () async {
      final api = _api(_device, (request) async => http.Response('{}', 401));
      try {
        await api.openActions();
        fail('expected ApiError');
      } on ApiError catch (error) {
        expect(error.unauthorized, true);
      }
    });

    testWidgets('alarm offers Pair again on revoked token',
        (tester) async {
      var repaired = false;
      await tester.pumpWidget(MaterialApp(
        home: AlarmScreen(
          action: PendingAction(
            runId: 'run1', domain: 'software', action: 'restart', detail: 'd',
            openedAt: 0, deadline: 20, autoApply: false,
          ),
          secondsLeft: 10,
          onDecide: (login, approve) async {},
          onSilence: () async {},
          error: 'Bad mobile token — re-pair this device.',
          unauthorized: true,
          onRepair: () async => repaired = true,
        ),
      ));
      await tester.scrollUntilVisible(
          find.text('Pair again'), 100,
          scrollable: find.byType(Scrollable));
      await tester.drag(find.byType(ListView), const Offset(0, -120));
      await tester.pumpAndSettle();
      expect(find.text('Pair again'), findsOneWidget);
      await tester.tap(find.text('Pair again'));
      expect(repaired, true);
    });

    testWidgets('plain errors show no Pair again', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: AlarmScreen(
          action: PendingAction(
            runId: 'run1', domain: 'software', action: 'restart', detail: 'd',
            openedAt: 0, deadline: 20, autoApply: false,
          ),
          secondsLeft: 10,
          onDecide: (login, approve) async {},
          onSilence: () async {},
          error: 'Too late — the server already decided.',
        ),
      ));
      expect(find.text('Pair again'), findsNothing);
    });
  });

  group('claim sign-in flow', () {
    test('claimAndConnect saves token + org', () async {
      final store = PairingStorage(storage: FakeSecureStorage());
      final container = ProviderContainer(overrides: [
        storageProvider.overrideWithValue(store),
      ]);
      addTearDown(container.dispose);
      final problem = await container
          .read(connectionProvider.notifier)
          .claimAndConnect(
            apiUrl: 'http://api:8201',
            code: '123-456',
            deviceName: 'pixel',
            client: MockClient((request) async {
              if (request.url.path == '/api/devices/claim') {
                return http.Response(
                    jsonEncode({
                      'device_token': 'ta_dev_new',
                      'org_id': 'org_acme'
                    }),
                    200);
              }
              return http.Response('{}', 200);
            }),
          );
      expect(problem, null);
      final saved = await store.load();
      expect(saved?.token, 'ta_dev_new');
      expect(saved?.orgId, 'org_acme');
      expect(container.read(connectionProvider).asData?.value?.token,
          'ta_dev_new');
    });

    test('bad code returns the message, saves nothing', () async {
      final store = PairingStorage(storage: FakeSecureStorage());
      final container = ProviderContainer(overrides: [
        storageProvider.overrideWithValue(store),
      ]);
      addTearDown(container.dispose);
      final problem = await container
          .read(connectionProvider.notifier)
          .claimAndConnect(
            apiUrl: 'http://api:8201',
            code: 'nope',
            deviceName: 'pixel',
            client: MockClient((request) async => http.Response('{}', 400)),
          );
      expect(problem, contains('didn’t work'));
      expect(await store.load(), null);
    });

    testWidgets('connect screen offers code claim', (tester) async {
      final store = PairingStorage(storage: FakeSecureStorage());
      await tester.pumpWidget(ProviderScope(
        overrides: [storageProvider.overrideWithValue(store)],
        child: const MaterialApp(home: ConnectScreen()),
      ));
      await tester.pumpAndSettle();
      expect(find.text('Pairing code (123-456)'), findsOneWidget);
      expect(find.text('Claim code & connect'), findsOneWidget);
      // Legacy self-hosted pairing stays alongside.
      expect(find.text('Mobile token (blank when unset)'), findsOneWidget);
    });
  });
}
