import 'agent_step.dart';
import 'pending_action.dart';

/// One row of GET /api/runs plus its detail payload.
class RunReport {
  const RunReport({
    required this.runId,
    required this.domain,
    required this.status,
    this.attempts = 0,
    this.modelUsed = '',
    this.source = '',
    this.stepCount = 0,
    this.decision,
    this.decisionDetail,
    this.steps = const [],
    this.result = const {},
  });

  final String runId;
  final String domain;
  final String status;
  final int attempts;
  final String modelUsed;
  final String source;
  final int stepCount;
  final String? decision;
  final PendingAction? decisionDetail;
  final List<AgentStep> steps;
  final Map<String, dynamic> result;

  factory RunReport.fromListJson(Map<String, dynamic> json) {
    return RunReport(
      runId: json['run_id'] as String? ?? '',
      domain: json['domain'] as String? ?? '',
      status: json['status'] as String? ?? '',
      attempts: (json['attempts'] as num?)?.toInt() ?? 0,
      modelUsed: json['model_used'] as String? ?? '',
      source: json['source'] as String? ?? '',
      stepCount: (json['n_steps'] as num?)?.toInt() ?? 0,
      decision: json['decision'] as String?,
    );
  }

  factory RunReport.fromDetailJson(Map<String, dynamic> json) {
    final rawSteps = json['steps'];
    final rawResult = json['result'];
    final rawDecision = json['decision'];
    return RunReport(
      runId: json['run_id'] as String? ?? '',
      domain: json['domain'] as String? ?? '',
      status: (rawResult is Map ? rawResult['status'] : null) as String? ?? '',
      steps: rawSteps is List
          ? rawSteps
              .whereType<Map>()
              .map((s) => AgentStep.fromJson(Map<String, dynamic>.from(s)))
              .toList()
          : const [],
      result: rawResult is Map ? Map<String, dynamic>.from(rawResult) : const {},
      decision: rawDecision is Map
          ? rawDecision['state'] as String?
          : rawDecision as String?,
      decisionDetail: rawDecision is Map
          ? PendingAction.fromJson(Map<String, dynamic>.from(rawDecision))
          : null,
    );
  }

  /// Sum of streamed stage wall times, for the "pipeline took …" header.
  double get pipelineMs =>
      steps.fold(0.0, (total, step) => total + step.durationMs);
}
