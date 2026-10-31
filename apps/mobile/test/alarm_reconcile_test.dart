import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telemetry_agent/models/pending_action.dart';
import 'package:telemetry_agent/providers.dart';
import 'package:telemetry_agent/services/alarm.dart';

PendingAction _action(String runId) => PendingAction(
      runId: runId,
      domain: 'software',
      action: 'Deploy the verified inventory patch to the shop',
      openedAt: 1000,
      deadline: DateTime.now().millisecondsSinceEpoch / 1000 + 20,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  ProviderContainer container() {
    final c = ProviderContainer(overrides: [
      socketProvider.overrideWithValue(null),
      alarmHardwareProvider.overrideWithValue(AlarmHardware(enabled: false)),
    ]);
    addTearDown(c.dispose);
    return c;
  }

  test('an alarm the server no longer has open is closed', () {
    final c = container();
    final alarm = c.read(alarmProvider.notifier);
    alarm.show(_action('r-1'));
    expect(c.read(alarmProvider)?.runId, 'r-1');
    alarm.reconcile([_action('r-1')]);
    expect(c.read(alarmProvider)?.runId, 'r-1');
    alarm.reconcile(const []);
    expect(c.read(alarmProvider), isNull);
  });

  test('the rehearsal alarm survives reconcile', () {
    final c = container();
    final alarm = c.read(alarmProvider.notifier);
    alarm.show(_action('rehearsal'));
    alarm.reconcile(const []);
    expect(c.read(alarmProvider)?.runId, 'rehearsal');
  });
}
