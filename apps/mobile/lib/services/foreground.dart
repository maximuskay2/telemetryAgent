import 'dart:io';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

/// Android foreground service: keeps the process (and socket) alive while
/// the phone is locked. The socket itself lives in the UI isolate; this
/// service only holds a visible keepalive notification so Android does not
/// suspend us mid-countdown. No-op off Android.
class Keepalive {
  static bool _started = false;

  static Future<void> start() async {
    if (_started || !Platform.isAndroid) return;
    try {
      FlutterForegroundTask.init(
        androidNotificationOptions: AndroidNotificationOptions(
          channelId: 'telemetry_keepalive',
          channelName: 'Agent connection',
          channelDescription: 'Keeps the incident socket alive',
          channelImportance: NotificationChannelImportance.LOW,
          priority: NotificationPriority.LOW,
        ),
        iosNotificationOptions:
            const IOSNotificationOptions(showNotification: false),
        foregroundTaskOptions: ForegroundTaskOptions(
          eventAction: ForegroundTaskEventAction.repeat(30000),
          allowWakeLock: true,
        ),
      );
      await FlutterForegroundTask.startService(
        serviceTypes: [ForegroundServiceTypes.dataSync],
        notificationTitle: 'Telemetry Agent connected',
        notificationText: 'Listening for veto windows',
        callback: _keepaliveCallback,
      );
      _started = true;
    } catch (_) {
      // Socket still works in the foreground.
    }
  }

  static Future<void> stop() async {
    if (!_started) return;
    _started = false;
    try {
      await FlutterForegroundTask.stopService();
    } catch (_) {
      // Already stopped.
    }
  }
}

@pragma('vm:entry-point')
void _keepaliveCallback() {
  FlutterForegroundTask.setTaskHandler(_KeepaliveHandler());
}

class _KeepaliveHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {}

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {}
}
