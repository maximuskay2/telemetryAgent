/// One streamed pipeline step (AgentStep), shared shape with the dashboard.
class AgentStep {
  const AgentStep({
    required this.step,
    this.attempt = 0,
    this.model = '',
    this.status = '',
    this.message = '',
    this.runId = '',
    this.domain = '',
    this.detail = '',
    this.source = '',
    this.durationMs = 0,
    this.suggestions = const [],
  });

  final String step;
  final int attempt;
  final String model;
  final String status;
  final String message;
  final String runId;
  final String domain;
  final String detail;
  final String source;
  final double durationMs;
  final List<String> suggestions;

  factory AgentStep.fromJson(Map<String, dynamic> json) {
    final rawSuggestions = json['suggestions'];
    return AgentStep(
      step: json['step'] as String? ?? '',
      attempt: (json['attempt'] as num?)?.toInt() ?? 0,
      model: json['model'] as String? ?? '',
      status: json['status'] as String? ?? '',
      message: json['message'] as String? ?? '',
      runId: json['run_id'] as String? ?? '',
      domain: json['domain'] as String? ?? '',
      detail: json['detail'] as String? ?? '',
      source: json['source'] as String? ?? '',
      durationMs: (json['duration_ms'] as num?)?.toDouble() ?? 0,
      suggestions: rawSuggestions is List
          ? rawSuggestions.whereType<String>().toList()
          : const [],
    );
  }

  /// Plain sentence for the activity feed, mirroring the dashboard wording.
  String sentence() {
    final short = detail.isNotEmpty ? _firstLine(detail, 120) : message;
    switch (step) {
      case 'diagnose':
        return 'Diagnosed: $short';
      case 'generate':
        return 'Wrote a fix (attempt $attempt)';
      case 'verify':
        return 'Sandbox verification: ${status.isNotEmpty ? status : 'ran'}';
      case 'done':
        final tail = message.isNotEmpty ? ' — ${_firstLine(message, 100)}' : '';
        if (status == 'FAIL' || status == 'error') {
          return 'Run finished: ${status.isNotEmpty ? status : 'error'}$tail';
        }
        if (status == 'NO_ACTION') {
          return 'Run finished: no action — normal behaviour$tail';
        }
        return 'Run finished: verified fix$tail';
      default:
        return '$step ${status.isNotEmpty ? status : ''}'.trim();
    }
  }

  static String _firstLine(String text, int max) {
    final line = text.split('\n').first.trim();
    return line.length > max ? '${line.substring(0, max)}…' : line;
  }
}
