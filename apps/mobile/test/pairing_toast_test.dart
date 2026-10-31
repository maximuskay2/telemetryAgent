import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:telemetry_agent/models/connection.dart';
import 'package:telemetry_agent/providers.dart';
import 'package:telemetry_agent/screens/settings_screen.dart';
import 'package:telemetry_agent/services/alarm.dart';
import 'package:telemetry_agent/services/storage.dart';
import 'package:telemetry_agent/services/toast.dart';

import 'commerce_app_test.dart' show FakeSecureStorage;

class _Root extends ConsumerWidget {
  const _Root();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final paired = ref.watch(connectionProvider).asData?.value != null;
    return Scaffold(body: Text(paired ? 'paired' : 'unpaired'));
  }
}

Future<ProviderContainer> _pump(WidgetTester tester, PairingStorage store) async {
  final container = ProviderContainer(overrides: [
    storageProvider.overrideWithValue(store),
    socketProvider.overrideWithValue(null),
    alarmHardwareProvider.overrideWithValue(AlarmHardware(enabled: false)),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(
      navigatorKey: rootNavigatorKey,
      scaffoldMessengerKey: rootMessengerKey,
      home: const _Root(),
    ),
  ));
  await tester.pumpAndSettle();
  return container;
}

void main() {
  testWidgets('unpair from Settings returns to the root and toasts',
      (tester) async {
    final store = PairingStorage(storage: FakeSecureStorage());
    await store.save(const Connection(
        apiUrl: 'http://api:8201', token: '', deviceName: 'pixel'));
    await _pump(tester, store);
    expect(find.text('paired'), findsOneWidget);
    rootNavigatorKey.currentState!.push(
        MaterialPageRoute(builder: (_) => const SettingsScreen()));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Unpair this device'), 200);
    await tester.tap(find.text('Unpair this device'));
    await tester.pumpAndSettle();
    expect(find.text('unpaired'), findsOneWidget);
    expect(find.byType(SettingsScreen), findsNothing);
    expect(find.text('Unpaired from http://api:8201'), findsOneWidget);
    expect(await store.load(), isNull);
  });

  testWidgets('pairing toasts success and failure', (tester) async {
    final store = PairingStorage(storage: FakeSecureStorage());
    final container = await _pump(tester, store);
    const connection =
        Connection(apiUrl: 'http://api:8201', token: '', deviceName: 'pixel');
    final failed = await container
        .read(connectionProvider.notifier)
        .saveAndConnect(connection,
            client: MockClient((_) async => http.Response('down', 503)));
    await tester.pump();
    expect(failed, isFalse);
    expect(find.text('Pairing failed — no agent at http://api:8201'),
        findsOneWidget);
    final ok = await container
        .read(connectionProvider.notifier)
        .saveAndConnect(connection,
            client: MockClient(
                (_) async => http.Response('{"status":"ok"}', 200)));
    await tester.pumpAndSettle();
    expect(ok, isTrue);
    expect(find.text('Paired with http://api:8201'), findsOneWidget);
  });
}
