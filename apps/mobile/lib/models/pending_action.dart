/// A server-owned veto window (M0 PendingAction).
class PendingAction {
  const PendingAction({
    required this.runId,
    required this.domain,
    required this.action,
    required this.openedAt,
    required this.deadline,
    this.state = 'pending',
    this.decidedBy,
    this.resolvedAt,
    this.detail = '',
  });

  final String runId;
  final String domain;
  final String action;
  final double openedAt;
  final double deadline;
  final String state;
  final String? decidedBy;
  final double? resolvedAt;
  final String detail;

  bool get isOpen => state == 'pending';

  int secondsLeft([DateTime? now]) {
    final current =
        (now ?? DateTime.now()).millisecondsSinceEpoch / 1000.0;
    return (deadline - current).ceil().clamp(0, 1 << 30);
  }

  factory PendingAction.fromJson(Map<String, dynamic> json) {
    return PendingAction(
      runId: json['run_id'] as String? ?? '',
      domain: json['domain'] as String? ?? '',
      action: json['action'] as String? ?? '',
      openedAt: (json['opened_at'] as num?)?.toDouble() ?? 0,
      deadline: (json['deadline'] as num?)?.toDouble() ?? 0,
      state: json['state'] as String? ?? 'pending',
      decidedBy: json['decided_by'] as String?,
      resolvedAt: (json['resolved_at'] as num?)?.toDouble(),
      detail: json['detail'] as String? ?? '',
    );
  }
}
