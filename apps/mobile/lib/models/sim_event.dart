/// Simulation / automation socket events (SimEvent kinds).
class SimEvent {
  const SimEvent({required this.kind, this.payload = const {}});

  final String kind;
  final Map<String, dynamic> payload;

  factory SimEvent.fromJson(Map<String, dynamic> json) {
    final raw = json['payload'];
    return SimEvent(
      kind: json['kind'] as String? ?? '',
      payload: raw is Map ? Map<String, dynamic>.from(raw) : const {},
    );
  }

  /// Plain sentence for the activity feed; null when the event stays visual.
  String? sentence() {
    switch (kind) {
      case 'watcher_trigger':
        return _watcherSentence();
      case 'fix_applied':
        return payload['domain'] == 'appliance'
            ? 'Runbook applied to fridge'
            : 'Fix applied to shop (merge and deploy)';
      case 'scenario_step':
        return 'Scenario step ${payload['done']}/${payload['total']}: '
            '${payload['action']}';
      case 'action_pending':
        return 'Veto window opened: ${payload['action']}';
      case 'action_resolved':
        return 'Action ${payload['state']}'
            '${payload['decided_by'] != null ? ' by ${payload['decided_by']}' : ''}';
      case 'gate_decision':
        return _gateSentence();
      case 'connection_status':
        return _connectionSentence();
      case 'actions_paused':
        return payload['paused'] == true
            ? 'Actions paused — nothing automatic will run'
            : 'Actions resumed';
      case 'pr_opened':
        return 'Fix PR opened: ${payload['pr_url'] ?? payload['repo'] ?? ''}';
      default:
        return null;
    }
  }

  String? _connectionSentence() {
    final status = payload['status'] as String?;
    final system = payload['system_id'] as String? ?? '';
    switch (status) {
      case 'ok':
        return 'Connected: $system ✓';
      case 'error':
        final detail = payload['detail'] as String? ?? 'connection error';
        return 'Connection error: $detail';
      default:
        return null;
    }
  }

  String? _gateSentence() {
    final decision = payload['decision'] as String?;
    final reason = payload['reason'] as String? ?? 'no reason given';
    final rule = payload['rule'] as String?;
    final ruleTag = rule != null && rule.isNotEmpty ? ' [$rule]' : '';
    switch (decision) {
      case 'suppress':
        final citation = payload['citation'] as String?;
        final citeTag =
            citation != null && citation.isNotEmpty ? ' ($citation)' : '';
        return 'Gate suppressed$ruleTag: $reason$citeTag';
      case 'observe':
        return 'Gate watching$ruleTag: $reason';
      case 'act':
        return 'Gate escalated$ruleTag: $reason';
      default:
        return null;
    }
  }

  String _watcherSentence() {
    final rule = payload['rule'] as String? ?? 'incident';
    final resource = payload['resource'] as String?;
    final on = resource != null && resource.isNotEmpty ? ' on $resource' : '';
    switch (rule) {
      case 'retry-cluster':
        return 'Watcher caught a retry storm$on';
      case 'deadlock':
        return 'Watcher caught a deadlock$on';
      case 'traceback':
        return 'Watcher caught a traceback$on';
      case 'error':
        return 'Watcher caught an error$on';
      case 'temp-warning':
      case 'temp-critical':
      case 'current-warning':
      case 'current-spike':
        final lines = payload['matched_lines'];
        final detail = lines is List && lines.isNotEmpty ? ': ${lines.first}' : '';
        return 'Sensor watcher caught $rule$detail';
      default:
        return 'Watcher caught $rule$on';
    }
  }
}
