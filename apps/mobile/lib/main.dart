import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'models/pending_action.dart';
import 'providers.dart';
import 'screens/alarm_screen.dart';
import 'screens/connect_screen.dart';
import 'screens/home_screen.dart';
import 'theme.dart';

void main() {
  runApp(const ProviderScope(child: TelemetryApp()));
}

class TelemetryApp extends ConsumerWidget {
  const TelemetryApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final connection = ref.watch(connectionProvider);
    final themeMode = ref.watch(themeModeProvider);
    return MaterialApp(
      title: 'Telemetry Agent',
      theme: telemetryLightTheme,
      darkTheme: telemetryDarkTheme,
      themeMode: themeMode,
      home: connection.when(
        data: (conn) => conn == null
            ? const ConnectScreen()
            : const AlarmNavigator(child: HomeScreen()),
        loading: () =>
            const Scaffold(body: Center(child: CircularProgressIndicator())),
        error: (_, _) => const ConnectScreen(),
      ),
    );
  }
}

/// Pushes the alarm screen when a veto window opens; notification taps
/// fetch the window and do the same (covers the killed-app case).
class AlarmNavigator extends ConsumerStatefulWidget {
  const AlarmNavigator({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<AlarmNavigator> createState() => _AlarmNavigatorState();
}

class _AlarmNavigatorState extends ConsumerState<AlarmNavigator> {
  static final _notifications = FlutterLocalNotificationsPlugin();
  bool _alarmOpen = false;
  bool _notificationsReady = false;

  @override
  void initState() {
    super.initState();
    _initNotifications();
  }

  Future<void> _initNotifications() async {
    if (_notificationsReady) return;
    _notificationsReady = true;
    try {
      await _notifications.initialize(
        settings: const InitializationSettings(
          android: AndroidInitializationSettings('@mipmap/ic_launcher'),
          iOS: DarwinInitializationSettings(),
        ),
        onDidReceiveNotificationResponse: _onNotificationTap,
      );
    } catch (_) {
      // Foreground socket navigation still works.
    }
  }

  Future<void> _onNotificationTap(NotificationResponse response) async {
    final runId = response.payload;
    final api = ref.read(apiProvider);
    if (runId == null || api == null) return;
    try {
      final open = await api.openActions();
      for (final action in open) {
        if (action.runId == runId) {
          ref.read(alarmProvider.notifier).show(action);
        }
      }
    } catch (_) {
      // Window already resolved.
    }
  }

  void _onAlarm(PendingAction? next) {
    if (next != null && next.isOpen && !_alarmOpen) {
      _alarmOpen = true;
      Navigator.of(context)
          .push(
            MaterialPageRoute(
              builder: (_) => AlarmRoute(action: next),
              fullscreenDialog: true,
            ),
          )
          .then((_) => _alarmOpen = false);
    } else if ((next == null || !next.isOpen) && _alarmOpen) {
      _alarmOpen = false;
      Navigator.of(context).popUntil((route) => route.isFirst);
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<PendingAction?>(alarmProvider, (_, next) => _onAlarm(next));
    return widget.child;
  }
}
