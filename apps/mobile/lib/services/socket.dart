import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/agent_step.dart';
import '../models/sim_event.dart';

/// Live socket with exponential-backoff reconnect. Emits one [FeedItem] per
/// event sentence plus raw log lines; visual-only events are skipped.
class AgentSocket {
  AgentSocket({required this.wsUri, this.onReconnect});

  final Uri wsUri;
  final void Function()? onReconnect;

  final _events = StreamController<FeedItem>.broadcast();
  final _state = StreamController<SocketState>.broadcast();
  final _actions = StreamController<SimEvent>.broadcast();

  Stream<FeedItem> get events => _events.stream;
  Stream<SocketState> get state => _state.stream;

  /// Raw automation events (action_pending/tick/resolved, …) for the alarm.
  Stream<SimEvent> get actions => _actions.stream;

  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _retry;
  bool _closed = false;
  int _attempt = 0;

  void connect() {
    _closed = false;
    _attempt = 0;
    _open();
  }

  void _open() {
    if (_closed) return;
    _state.add(SocketState.connecting);
    try {
      final channel = WebSocketChannel.connect(wsUri);
      _channel = channel;
      var first = _attempt > 0;
      _subscription = channel.stream.listen(
        (raw) {
          _attempt = 0;
          if (first) {
            first = false;
            onReconnect?.call();
          }
          _state.add(SocketState.live);
          final item = FeedItem.parse(raw);
          if (item != null) _events.add(item);
          final action = _parseSimEvent(raw);
          if (action != null) _actions.add(action);
        },
        onError: (_) => _scheduleRetry(),
        onDone: () => _scheduleRetry(),
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleRetry();
    }
  }

  void _scheduleRetry() {
    if (_closed) return;
    _subscription?.cancel();
    _subscription = null;
    _state.add(SocketState.retrying);
    _attempt += 1;
    final delay = Duration(seconds: _attempt < 5 ? 1 << _attempt : 30);
    _retry?.cancel();
    _retry = Timer(delay, _open);
  }

  Future<void> close() async {
    _closed = true;
    _retry?.cancel();
    await _subscription?.cancel();
    await _channel?.sink.close();
    await _events.close();
    await _state.close();
    await _actions.close();
  }

  static SimEvent? _parseSimEvent(dynamic raw) {
    try {
      final decoded = raw is String ? jsonDecode(raw) : raw;
      if (decoded is Map && decoded['kind'] is String) {
        return SimEvent.fromJson(Map<String, dynamic>.from(decoded));
      }
    } catch (_) {
      // Not an event; the feed parser already said so.
    }
    return null;
  }
}

enum SocketState { connecting, live, retrying }

/// One feed row: a sentence plus an optional violet model tag.
class FeedItem {
  const FeedItem({
    required this.source,
    required this.message,
    this.level = 'INFO',
    this.tag,
    this.at,
  });

  final String source;
  final String message;
  final String level;
  final String? tag;
  final DateTime? at;

  static FeedItem? parse(dynamic raw) {
    Map<String, dynamic>? json;
    try {
      final decoded = raw is String ? jsonDecode(raw) : raw;
      if (decoded is Map) json = Map<String, dynamic>.from(decoded);
    } catch (_) {
      return null;
    }
    if (json == null) return null;
    if (json['step'] is String) {
      final step = AgentStep.fromJson(json);
      if (step.domain != 'software' && step.domain != 'appliance') {
        return null;
      }
      final failed = step.status == 'FAIL' || step.status == 'error';
      return FeedItem(
        source: 'agent',
        message: step.sentence(),
        level: failed ? 'ERROR' : 'INFO',
        tag: step.model.isNotEmpty ? step.model : null,
        at: DateTime.now(),
      );
    }
    if (json['kind'] is String) {
      final event = SimEvent.fromJson(json);
      final sentence = event.sentence();
      if (sentence == null) return null;
      return FeedItem(
        source: _sourceFor(event.kind),
        message: sentence,
        level: _levelFor(event),
        at: DateTime.now(),
      );
    }
    if (json['message'] is String) {
      return FeedItem(
        source: json['source'] as String? ?? 'log',
        message: json['message'] as String,
        level: json['level'] as String? ?? 'INFO',
        at: DateTime.now(),
      );
    }
    return null;
  }

  static String _sourceFor(String kind) {
    switch (kind) {
      case 'watcher_trigger':
        return 'watcher';
      case 'fix_applied':
        return 'fix';
      case 'scenario_step':
        return 'scenario';
      case 'gate_decision':
        return 'gate';
      case 'action_pending':
      case 'action_tick':
      case 'action_resolved':
        return 'action';
      default:
        return kind;
    }
  }

  /// Gate verdicts colour the feed row: grey when suppressed, amber when
  /// watching, red when escalated. Everything else stays INFO.
  static String _levelFor(SimEvent event) {
    if (event.kind != 'gate_decision') return 'INFO';
    switch (event.payload['decision']) {
      case 'suppress':
        return 'DEBUG';
      case 'observe':
        return 'WARNING';
      case 'act':
        return 'ERROR';
      default:
        return 'INFO';
    }
  }
}
