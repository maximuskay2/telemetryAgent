import 'dart:async';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:vibration/vibration.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../models/pending_action.dart';

/// Alarm hardware: looping siren, vibration pattern, wake lock, and the
/// Android alarm channel with full-screen intent. All platform calls are
/// best-effort — a silent alarm must still show the screen.
class AlarmHardware {
  AlarmHardware({AudioPlayer? player, this.enabled = true})
      : _player = player ?? AudioPlayer();

  final AudioPlayer _player;
  final bool enabled;
  Timer? _buzzTimer;
  bool _ringing = false;
  bool _urgent = false;

  bool get ringing => _ringing;

  /// Last-5-seconds escalation: buzz twice as often until stopped.
  void setUrgent(bool urgent) {
    if (_urgent == urgent || !_ringing) {
      _urgent = urgent;
      return;
    }
    _urgent = urgent;
    _startBuzz();
  }

  static const _channel = AndroidNotificationChannel(
    'telemetry_alarm',
    'Incident alarms',
    description: 'Veto-window alarms that wake the phone',
    importance: Importance.max,
    playSound: true,
    sound: RawResourceAndroidNotificationSound('alarm'),
    audioAttributesUsage: AudioAttributesUsage.alarm,
  );

  /// Quiet channel for gate "watching" verdicts: no sound, no vibration,
  /// no full-screen intent — the feed row carries the detail.
  static const _quietChannel = AndroidNotificationChannel(
    'telemetry_watch',
    'Watching',
    description: 'Quiet gate observations',
    importance: Importance.low,
    playSound: false,
    enableVibration: false,
  );

  static final _notifications = FlutterLocalNotificationsPlugin();
  static bool _channelReady = false;

  /// Create the alarm channel once; returns false when notifications fail.
  static Future<bool> ensureChannel() async {
    if (_channelReady) return true;
    try {
      final android =
          _notifications.resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>();
      if (android != null) {
        await android.requestNotificationsPermission();
        await android.createNotificationChannel(_channel);
        await android.createNotificationChannel(_quietChannel);
      }
      _channelReady = true;
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Fire the full-screen alarm notification; tap opens the alarm screen.
  static Future<void> fire(PendingAction action) async {
    try {
      await ensureChannel();
      await _notifications.show(
        id: action.runId.hashCode,
        title: action.ready
            ? 'VETO ${action.secondsLeft()}s — ${action.domain} fix'
            : 'FIX READY — verifying ${action.domain} fix',
        body: action.action,
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails(
            _channel.id,
            _channel.name,
            channelDescription: _channel.description,
            importance: Importance.max,
            priority: Priority.max,
            category: AndroidNotificationCategory.alarm,
            fullScreenIntent: true,
            sound: _channel.sound,
            audioAttributesUsage: AudioAttributesUsage.alarm,
            autoCancel: false,
            ongoing: true,
          ),
          iOS: const DarwinNotificationDetails(
            presentAlert: true,
            presentSound: true,
            interruptionLevel: InterruptionLevel.timeSensitive,
          ),
        ),
        payload: action.runId,
      );
    } catch (_) {
      // Screen navigation still carries the alarm.
    }
  }

  static Future<void> cancel(PendingAction action) async {
    try {
      await _notifications.cancel(id: action.runId.hashCode);
    } catch (_) {
      // Already gone.
    }
  }

  /// Quiet heads-up for a gate "watching" verdict. Suppressed candidates
  /// never notify; escalated ones ring through the normal alarm flow.
  static Future<void> notifyQuiet({
    required String title,
    required String body,
    String tag = 'gate-observe',
  }) async {
    try {
      await ensureChannel();
      await _notifications.show(
        id: tag.hashCode,
        title: title,
        body: body,
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails(
            _quietChannel.id,
            _quietChannel.name,
            channelDescription: _quietChannel.description,
            importance: Importance.low,
            priority: Priority.low,
            autoCancel: true,
            ongoing: false,
          ),
          iOS: const DarwinNotificationDetails(
            presentAlert: true,
            presentSound: false,
            interruptionLevel: InterruptionLevel.passive,
          ),
        ),
        payload: tag,
      );
    } catch (_) {
      // The feed row still carries the verdict.
    }
  }

  Future<void> ring() async {
    if (_ringing || !enabled) return;
    _ringing = true;
    try {
      await _player.setReleaseMode(ReleaseMode.loop);
      await _player.play(AssetSource('alarm.wav'));
    } catch (_) {
      // Keep vibrating + flashing without audio.
    }
    try {
      if (Platform.isAndroid || Platform.isIOS) {
        await WakelockPlus.enable();
      }
    } catch (_) {
      // Screen may sleep; the countdown survives.
    }
    _startBuzz();
  }

  void _startBuzz() {
    _buzzTimer?.cancel();
    // A short tick every second; a double-strong pattern in the last 5 s.
    _buzzTimer = Timer.periodic(const Duration(seconds: 1), (_) async {
      try {
        if (await Vibration.hasVibrator()) {
          await Vibration.vibrate(
              pattern: _urgent ? [0, 600, 100, 600] : [0, 80]);
        }
      } catch (_) {
        // No vibrator, no problem.
      }
    });
  }

  Future<void> stop() async {
    _ringing = false;
    _urgent = false;
    _buzzTimer?.cancel();
    _buzzTimer = null;
    try {
      await _player.stop();
    } catch (_) {
      // Already silent.
    }
    try {
      await WakelockPlus.disable();
    } catch (_) {
      // Already released.
    }
  }
}
