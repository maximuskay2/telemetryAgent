import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'models/pending_action.dart';
import 'providers.dart';
import 'screens/alarm_screen.dart';
import 'screens/connect_screen.dart';
import 'screens/home_screen.dart';
import 'services/toast.dart';
import 'theme.dart';

void main() {
  runApp(const ProviderScope(child: TelemetryApp()));
}

class TelemetryApp extends ConsumerWidget {
  const TelemetryApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);
    return MaterialApp(
      title: 'Telemetry Agent',
      navigatorKey: rootNavigatorKey,
      scaffoldMessengerKey: rootMessengerKey,
      theme: telemetryLightTheme,
      darkTheme: telemetryDarkTheme,
      themeMode: themeMode,
      home: const AppRoot(),
    );
  }
}

/// Pairing screen or the paired app; rebuilds itself when pairing changes.
class AppRoot extends ConsumerWidget {
  const AppRoot({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref.watch(connectionProvider).when(
          data: (conn) => conn == null
              ? const ConnectScreen()
              : const AlarmNavigator(child: HomeScreen()),
          loading: () => const Scaffold(
              body: Center(child: CircularProgressIndicator())),
          error: (_, _) => const ConnectScreen(),
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
  Route<void>? _alarmRoute;
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
    final open = _alarmRoute;
    if (next != null && next.isOpen && open == null) {
      final route = MaterialPageRoute<void>(
        builder: (_) => AlarmRoute(action: next),
        fullscreenDialog: true,
      );
      _alarmRoute = route;
      Navigator.of(context).push(route).then((_) {
        if (_alarmRoute == route) _alarmRoute = null;
      });
    } else if ((next == null || !next.isOpen) && open != null) {
      // Only close the alarm itself: a decision may already have replaced
      // it with the outcome screen, which must stay until "Back to feed".
      _alarmRoute = null;
      if (open.isCurrent) Navigator.of(context).removeRoute(open);
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<PendingAction?>(alarmProvider, (_, next) => _onAlarm(next));
    return widget.child;
  }
}
