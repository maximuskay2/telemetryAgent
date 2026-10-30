import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'models/connection.dart';
import 'models/pending_action.dart';
import 'models/production.dart';
import 'models/run_report.dart';
import 'models/sim_event.dart';
import 'services/alarm.dart';
import 'services/api.dart';
import 'services/foreground.dart';
import 'services/socket.dart';
import 'services/storage.dart';
import 'theme.dart';

final storageProvider = Provider<PairingStorage>((ref) => PairingStorage());

/// Color mode, persisted across restarts. Light is the default; the
/// saved choice wins. Syncs AppTheme so direct palette reads agree.
final themeModeProvider =
    NotifierProvider<ThemeModeNotifier, ThemeMode>(ThemeModeNotifier.new);

class ThemeModeNotifier extends Notifier<ThemeMode> {
  static const key = 'ta-theme-mode';

  @override
  ThemeMode build() {
    _load();
    return ThemeMode.light;
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(key);
    final mode = saved == 'dark' ? ThemeMode.dark : ThemeMode.light;
    AppTheme.mode = mode;
    state = mode;
  }

  Future<void> setMode(ThemeMode mode) async {
    AppTheme.mode = mode;
    state = mode;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(key, mode == ThemeMode.dark ? 'dark' : 'light');
  }
}

/// Saved pairing, or null when the app needs the Connect screen.
final connectionProvider =
    AsyncNotifierProvider<ConnectionNotifier, Connection?>(
        ConnectionNotifier.new);

class ConnectionNotifier extends AsyncNotifier<Connection?> {
  @override
  Future<Connection?> build() => ref.read(storageProvider).load();

  Future<bool> saveAndConnect(Connection connection,
      {http.Client? client}) async {
    final api = AgentApi(connection: connection, client: client);
    final ok = await api.checkHealth();
    api.close();
    if (!ok) return false;
    await ref.read(storageProvider).save(connection);
    state = AsyncData(connection);
    unawaited(Keepalive.start());
    return true;
  }

  Future<void> disconnect() async {
    await ref.read(storageProvider).clear();
    unawaited(Keepalive.stop());
    state = const AsyncData(null);
  }

  /// Per-user sign-in (C-N4): claim a web pairing code, then connect
  /// with the device token. Returns an error message, or null on success.
  Future<String?> claimAndConnect({
    required String apiUrl,
    required String code,
    required String deviceName,
    http.Client? client,
  }) async {
    final probe = AgentApi(
      connection: Connection(apiUrl: apiUrl, token: '', deviceName: ''),
      client: client,
    );
    try {
      final claimed = await probe.claim(code);
      if (claimed.deviceToken.isEmpty) return 'That code didn’t work.';
      return await saveAndConnect(
        Connection(
          apiUrl: apiUrl,
          token: claimed.deviceToken,
          deviceName: deviceName,
          orgId: claimed.orgId,
        ),
        client: client,
      )
          ? null
          : 'No agent at that URL — same Wi-Fi? API running?';
    } on ApiError catch (error) {
      return error.message;
    } finally {
      probe.close();
    }
  }
}

final apiProvider = Provider<AgentApi?>((ref) {
  final connection = ref.watch(connectionProvider).asData?.value;
  if (connection == null) return null;
  final api = AgentApi(connection: connection);
  ref.onDispose(api.close);
  return api;
});

/// Live socket; reconnects with backoff and resyncs open actions.
final socketProvider = Provider<AgentSocket?>((ref) {
  final connection = ref.watch(connectionProvider).asData?.value;
  if (connection == null) return null;
  final socket = AgentSocket(
    wsUri: connection.wsUri,
    onReconnect: () {
      ref.invalidate(openActionsProvider);
      ref.invalidate(runsProvider);
    },
  );
  socket.connect();
  ref.onDispose(() => unawaited(socket.close()));
  return socket;
});

final socketStateProvider = StreamProvider<SocketState>((ref) async* {
  final socket = ref.watch(socketProvider);
  if (socket == null) {
    yield SocketState.connecting;
    return;
  }
  yield* socket.state;
});

/// Rolling live feed (newest first, capped).
class FeedNotifier extends Notifier<List<FeedItem>> {
  StreamSubscription? _subscription;

  @override
  List<FeedItem> build() {
    final socket = ref.watch(socketProvider);
    _subscription?.cancel();
    if (socket != null) {
      _subscription = socket.events.listen((item) {
        state = [item, ...state].take(100).toList();
      });
    }
    ref.onDispose(() => _subscription?.cancel());
    return const [];
  }
}

final feedProvider =
    NotifierProvider<FeedNotifier, List<FeedItem>>(FeedNotifier.new);

/// Open veto windows, refreshed on reconnect and by the alarm flow.
final openActionsProvider =
    FutureProvider.autoDispose<List<PendingAction>>((ref) async {
  final api = ref.watch(apiProvider);
  if (api == null) return const [];
  return api.openActions();
});

/// One-second heartbeat so on-screen countdowns tick locally.
final clockProvider = StreamProvider.autoDispose<int>((ref) async* {
  var tick = 0;
  while (true) {
    await Future<void>.delayed(const Duration(seconds: 1));
    yield tick++;
  }
});

final alarmHardwareProvider = Provider<AlarmHardware>((ref) {
  final hardware = AlarmHardware();
  ref.onDispose(() => unawaited(hardware.stop()));
  return hardware;
});

/// Last server tick for the ringing window (plain field: the route already
/// rebuilds every second, so no notification is needed).
class ServerTick {
  const ServerTick(this.runId, this.left, this.at);

  final String runId;
  final int left;
  final DateTime at;
}

/// Currently ringing veto window, driven by action_pending/resolved events.
class AlarmNotifier extends Notifier<PendingAction?> {
  StreamSubscription? _subscription;
  ServerTick? lastTick;

  @override
  PendingAction? build() {
    final socket = ref.watch(socketProvider);
    _subscription?.cancel();
    lastTick = null;
    if (socket != null) {
      _subscription = socket.actions.listen(_onEvent);
    }
    ref.onDispose(() => _subscription?.cancel());
    return null;
  }

  void show(PendingAction action) {
    if (state?.runId == action.runId) return;
    state = action;
    final hardware = ref.read(alarmHardwareProvider);
    unawaited(hardware.ring());
    unawaited(AlarmHardware.fire(action));
  }

  Future<void> silence() async {
    final action = state;
    state = null;
    await ref.read(alarmHardwareProvider).stop();
    if (action != null) await AlarmHardware.cancel(action);
  }

  void _onEvent(SimEvent event) {
    if (event.kind == 'action_pending') {
      lastTick = null;
      show(PendingAction.fromJson(event.payload));
    } else if (event.kind == 'gate_decision' &&
        event.payload['decision'] == 'observe') {
      final reason = event.payload['reason'] as String? ?? 'watching';
      final rule = event.payload['rule'] as String? ?? '';
      unawaited(AlarmHardware.notifyQuiet(
        title: rule.isEmpty ? 'Gate watching' : 'Gate watching: $rule',
        body: reason,
      ));
    } else if (event.kind == 'action_tick') {
      final runId = event.payload['run_id'] as String?;
      final left = (event.payload['seconds_left'] as num?)?.toInt();
      if (runId != null && left != null && state?.runId == runId) {
        lastTick = ServerTick(runId, left, DateTime.now());
      }
    } else if (event.kind == 'action_resolved') {
      final runId = event.payload['run_id'] as String?;
      ref.invalidate(runsProvider);
      if (runId != null) ref.invalidate(runDetailProvider(runId));
      if (runId != null && state?.runId == runId) {
        unawaited(silence());
      }
    } else if (event.kind == 'option_status') {
      final runId = event.payload['run_id'] as String?;
      if (runId != null) ref.invalidate(incidentOptionsProvider(runId));
    } else if (event.kind == 'actions_paused') {
      final paused = event.payload['paused'] == true;
      ref.read(pauseProvider.notifier).applyRemote(paused);
    } else if (event.kind == 'pr_opened') {
      final runId = event.payload['run_id'] as String?;
      final prUrl = event.payload['pr_url'] as String? ?? '';
      ref.invalidate(runsProvider);
      if (runId != null) {
        ref.invalidate(runDetailProvider(runId));
        ref.invalidate(incidentOptionsProvider(runId));
      }
      unawaited(AlarmHardware.notifyQuiet(
        title: 'Fix PR ready',
        body: prUrl.isEmpty ? 'Review the pull request.' : prUrl,
      ));
    }
  }
}

/// Production fix options for one incident, refreshed live by
/// option_status events.
final incidentOptionsProvider = FutureProvider.autoDispose
    .family<IncidentOptions, String>((ref, runId) async {
  final api = ref.watch(apiProvider);
  if (api == null) throw const ApiError('Not connected.');
  return api.incidentOptions(runId);
});

/// Global pause switch, kept in sync by actions_paused events.
final pauseProvider =
    AsyncNotifierProvider<PauseNotifier, bool>(PauseNotifier.new);

class PauseNotifier extends AsyncNotifier<bool> {
  @override
  Future<bool> build() async {
    final api = ref.watch(apiProvider);
    if (api == null) return false;
    return api.getPaused();
  }

  Future<void> setPaused(bool paused) async {
    final api = ref.read(apiProvider);
    if (api == null) return;
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => api.setPaused(paused));
  }

  void applyRemote(bool paused) {
    state = AsyncData(paused);
  }
}

final alarmProvider =
    NotifierProvider<AlarmNotifier, PendingAction?>(AlarmNotifier.new);

/// M4 report filters (roadmap: open, auto-applied, approved, disapproved,
/// failed — plus "all" for the unfiltered feed).
enum ReportFilter {
  all,
  open,
  autoApplied,
  approved,
  disapproved,
  failed,
  ignored,
}

extension ReportFilterMatch on ReportFilter {
  String get label {
    switch (this) {
      case ReportFilter.all:
        return 'All';
      case ReportFilter.open:
        return 'Open';
      case ReportFilter.autoApplied:
        return 'Auto-applied';
      case ReportFilter.approved:
        return 'Approved';
      case ReportFilter.disapproved:
        return 'Disapproved';
      case ReportFilter.failed:
        return 'Failed';
      case ReportFilter.ignored:
        return 'Ignored';
    }
  }

  bool matches(RunReport run) {
    switch (this) {
      case ReportFilter.all:
        return true;
      case ReportFilter.open:
        return run.decision == 'pending';
      case ReportFilter.autoApplied:
        return run.decision == 'auto_applied';
      case ReportFilter.approved:
        return run.decision == 'approved';
      case ReportFilter.disapproved:
        return run.decision == 'disapproved';
      case ReportFilter.failed:
        return run.decision == 'failed' || run.status == 'FAIL';
      case ReportFilter.ignored:
        return run.gate?.decision == 'suppress';
    }
  }
}

final reportFilterProvider =
    NotifierProvider<ReportFilterNotifier, ReportFilter>(
        ReportFilterNotifier.new);

class ReportFilterNotifier extends Notifier<ReportFilter> {
  @override
  ReportFilter build() => ReportFilter.all;

  void set(ReportFilter filter) => state = filter;
}

/// Incident list: polls every 5 s; refreshed on reconnect and every veto
/// resolution so the feed follows live updates.
final runsProvider =
    FutureProvider.autoDispose<List<RunReport>>((ref) async {
  final api = ref.watch(apiProvider);
  if (api == null) return const [];
  final timer =
      Timer(const Duration(seconds: 5), () => ref.invalidateSelf());
  ref.onDispose(timer.cancel);
  return api.runs();
});

/// One incident report, refreshed when its veto window resolves.
final runDetailProvider =
    FutureProvider.autoDispose.family<RunReport, String>((ref, runId) async {
  final api = ref.watch(apiProvider);
  if (api == null) throw const ApiError('Not connected.');
  return api.runDetail(runId);
});

/// Recent fridge readings captured from the live stream (for the charts
/// on appliance reports; the server keeps no per-run history).
class TempSample {
  const TempSample(this.at, this.celsius, this.amps, this.vibrationG);

  final DateTime at;
  final double celsius;
  final double amps;
  final double vibrationG;
}

class FridgeTempsNotifier extends Notifier<List<TempSample>> {
  StreamSubscription? _subscription;

  @override
  List<TempSample> build() {
    final socket = ref.watch(socketProvider);
    _subscription?.cancel();
    if (socket != null) {
      _subscription = socket.actions.listen((event) {
        if (event.kind != 'fridge_reading') return;
        final reading = event.payload['reading'];
        if (reading is! Map) return;
        final temp = (reading['temperature_c'] as num?)?.toDouble();
        if (temp == null) return;
        final amps = (reading['current_a'] as num?)?.toDouble() ?? 0;
        final vib = (reading['vibration_g'] as num?)?.toDouble() ?? 0;
        final next = [
          ...state,
          TempSample(DateTime.now(), temp, amps, vib)
        ];
        state = next.length > 120
            ? next.sublist(next.length - 120)
            : next;
      });
    }
    ref.onDispose(() => _subscription?.cancel());
    return const [];
  }
}

final fridgeTempsProvider =
    NotifierProvider<FridgeTempsNotifier, List<TempSample>>(
        FridgeTempsNotifier.new);

/// Monitored systems, for feed card names.
final systemsProvider =
    FutureProvider.autoDispose<List<SystemSummary>>((ref) async {
  final api = ref.watch(apiProvider);
  if (api == null) return const [];
  return api.systems();
});

/// Normal temperature band from a system's profile (normal_ranges first,
/// hard limits as a net). Null when the profile has neither.
final profileBandProvider = FutureProvider.autoDispose
    .family<({double min, double max})?, String>((ref, systemId) async {
  final api = ref.watch(apiProvider);
  if (api == null || systemId.isEmpty) return null;
  final profile = await api.profile(systemId);
  bool isTemp(Object? metric) =>
      metric == 'temp_c' || metric == 'temperature_c';
  final ranges = profile['normal_ranges'];
  if (ranges is List) {
    for (final row in ranges.whereType<Map>()) {
      final min = (row['min'] as num?)?.toDouble();
      final max = (row['max'] as num?)?.toDouble();
      if (isTemp(row['metric']) && min != null && max != null) {
        return (min: min, max: max);
      }
    }
  }
  final limits = profile['hard_limits'];
  if (limits is! List) return null;
  var min = 2.0;
  var max = 8.0;
  var found = false;
  for (final row in limits.whereType<Map>()) {
    final threshold = row['threshold'] as num?;
    final value = row['value'] as num?;
    final limit = (threshold ?? value)?.toDouble();
    if (!isTemp(row['metric']) || limit == null) continue;
    final op = row['op'] as String?;
    if (op == 'gt' || op == '>' || op == '>=') {
      if (limit < max) max = limit;
      found = true;
    } else if (op == 'lt' || op == '<' || op == '<=') {
      if (limit > min) min = limit;
      found = true;
    }
  }
  return found ? (min: min, max: max) : null;
});
