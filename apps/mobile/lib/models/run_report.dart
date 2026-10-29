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
    this.gate,
    this.steps = const [],
    this.result = const {},
    this.verification,
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
  final GateDecision? gate;
  final List<AgentStep> steps;
  final Map<String, dynamic> result;
  final Map<String, dynamic>? verification;

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
      gate: json['gate_decision'] is String
          ? GateDecision(
              decision: json['gate_decision'] as String,
              reason: '',
              citation: '',
            )
          : null,
    );
  }

  factory RunReport.fromDetailJson(Map<String, dynamic> json) {
    final rawSteps = json['steps'];
    final rawResult = json['result'];
    final rawDecision = json['decision'];
    final rawGate = json['gate'];
    final rawVerification = json['verification'];
    final nestedVerification =
        rawResult is Map ? rawResult['verification'] : null;
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
      gate: rawGate is Map
          ? GateDecision.fromJson(Map<String, dynamic>.from(rawGate))
          : null,
      // S1's optional fail-to-pass evidence: top-level sibling first, then
      // the copy nested in result. Pre-S1 runs have neither (null-safe).
      verification: rawVerification is Map
          ? Map<String, dynamic>.from(rawVerification)
          : nestedVerification is Map
              ? Map<String, dynamic>.from(nestedVerification)
              : null,
    );
  }

  /// Sum of streamed stage wall times, for the "pipeline took …" header.
  double get pipelineMs =>
      steps.fold(0.0, (total, step) => total + step.durationMs);

  /// S1 evidence, all optional so pre-S1 reports still render.
  String get verificationRunner =>
      verification?['runner'] as String? ?? '';

  bool get verifyFailedOnOriginal =>
      (verification?['original'] as Map?)?['passed'] == false;

  bool get verifyPassedOnPatch =>
      (verification?['patched'] as Map?)?['passed'] == true;

  /// "Verified: tests fail→pass in {runner}" or '' when no evidence.
  String get verifyLine {
    if (!verifyFailedOnOriginal || !verifyPassedOnPatch) return '';
    final runner = verificationRunner;
    return runner.isEmpty
        ? 'Verified: tests fail→pass'
        : 'Verified: tests fail→pass in $runner';
  }
}

/// The setup gate's verdict for the candidate behind this run:
/// suppress / observe / act, with reason, citation, and per-check detail.
class GateDecision {
  const GateDecision({
    required this.decision,
    required this.reason,
    required this.citation,
    this.checks = const [],
    this.systemId = '',
  });

  final String decision;
  final String reason;
  final String citation;
  final List<GateCheck> checks;
  final String systemId;

  factory GateDecision.fromJson(Map<String, dynamic> json) {
    final rawChecks = json['checks'];
    return GateDecision(
      decision: json['decision'] as String? ?? '',
      reason: json['reason'] as String? ?? '',
      citation: json['citation'] as String? ?? '',
      systemId: json['system_id'] as String? ?? '',
      checks: rawChecks is List
          ? rawChecks
              .whereType<Map>()
              .map((c) => GateCheck.fromJson(Map<String, dynamic>.from(c)))
              .toList()
          : const [],
    );
  }

  /// Short display label for the verdict chip.
  String get label => switch (decision) {
        'suppress' => 'Suppressed',
        'observe' => 'Watching',
        'act' => 'Escalated',
        _ => decision,
      };
}

/// One gate check row: hard_limit / armed / expected / mode / baseline / impact.
class GateCheck {
  const GateCheck({
    required this.name,
    required this.result,
    required this.detail,
  });

  final String name;
  final String result;
  final String detail;

  factory GateCheck.fromJson(Map<String, dynamic> json) {
    return GateCheck(
      name: json['name'] as String? ?? '',
      result: json['result'] as String? ?? '',
      detail: json['detail'] as String? ?? '',
    );
  }
}
