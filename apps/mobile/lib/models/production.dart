/// Production-route models (production-roadmap §3.4, frozen at H0).
///
/// Hand-mirrored from `core/schemas/production.py`; JSON keys stay
/// snake_case exactly as the API sends them.
class ProdConnection {
  const ProdConnection({
    required this.id,
    required this.systemId,
    required this.kind,
    this.config = const {},
    this.secretHint = '',
    this.status = 'waiting',
    this.detail = '',
    this.lastSeen = 0,
  });

  final String id;
  final String systemId;
  final String kind;
  final Map<String, dynamic> config;
  final String secretHint;
  final String status;
  final String detail;
  final double lastSeen;

  factory ProdConnection.fromJson(Map<String, dynamic> json) {
    final config = json['config'];
    return ProdConnection(
      id: json['id'] as String? ?? '',
      systemId: json['system_id'] as String? ?? '',
      kind: json['kind'] as String? ?? '',
      config: config is Map ? Map<String, dynamic>.from(config) : const {},
      secretHint: json['secret_hint'] as String? ?? '',
      status: json['status'] as String? ?? 'waiting',
      detail: json['detail'] as String? ?? '',
      lastSeen: (json['last_seen'] as num?)?.toDouble() ?? 0,
    );
  }
}

class ConnectionTestResult {
  const ConnectionTestResult({
    required this.ok,
    this.detail = '',
    this.canRead = false,
    this.canOpenPrs = false,
    this.hasPermissions = false,
  });

  final bool ok;
  final String detail;
  final bool canRead;
  final bool canOpenPrs;
  final bool hasPermissions;

  factory ConnectionTestResult.fromJson(Map<String, dynamic> json) {
    final permissions = json['permissions'];
    final perms =
        permissions is Map ? Map<String, dynamic>.from(permissions) : null;
    return ConnectionTestResult(
      ok: json['ok'] as bool? ?? false,
      detail: json['detail'] as String? ?? '',
      canRead: perms?['read'] as bool? ?? false,
      canOpenPrs: perms?['pull_requests'] as bool? ?? false,
      hasPermissions: perms != null,
    );
  }
}

class OptionSafety {
  const OptionSafety({required this.ok, this.reason = ''});

  final bool ok;
  final String reason;

  factory OptionSafety.fromJson(Map<String, dynamic> json) {
    return OptionSafety(
      ok: json['ok'] as bool? ?? false,
      reason: json['reason'] as String? ?? '',
    );
  }
}

class ProdOption {
  const ProdOption({
    required this.id,
    required this.kind,
    required this.title,
    this.detail = '',
    this.url = '',
    this.safety = const OptionSafety(ok: true),
    this.status = 'available',
  });

  final String id;
  final String kind;
  final String title;
  final String detail;
  final String url;
  final OptionSafety safety;
  final String status;

  bool get executable => safety.ok && status == 'available';

  factory ProdOption.fromJson(Map<String, dynamic> json) {
    final safety = json['safety'];
    return ProdOption(
      id: json['id'] as String? ?? '',
      kind: json['kind'] as String? ?? '',
      title: json['title'] as String? ?? '',
      detail: json['detail'] as String? ?? '',
      url: json['url'] as String? ?? '',
      safety: safety is Map
          ? OptionSafety.fromJson(Map<String, dynamic>.from(safety))
          : const OptionSafety(ok: true),
      status: json['status'] as String? ?? 'available',
    );
  }
}

class IncidentOptions {
  const IncidentOptions({
    required this.runId,
    required this.domain,
    this.options = const [],
  });

  final String runId;
  final String domain;
  final List<ProdOption> options;

  factory IncidentOptions.fromJson(Map<String, dynamic> json) {
    final options = json['options'];
    return IncidentOptions(
      runId: json['run_id'] as String? ?? '',
      domain: json['domain'] as String? ?? '',
      options: options is List
          ? options
              .whereType<Map>()
              .map((o) => ProdOption.fromJson(Map<String, dynamic>.from(o)))
              .toList()
          : const [],
    );
  }
}

class DeviceCommandItem {
  const DeviceCommandItem({
    required this.id,
    required this.action,
    this.params = const {},
    this.expiresAt = 0,
  });

  final String id;
  final String action;
  final Map<String, dynamic> params;
  final double expiresAt;

  factory DeviceCommandItem.fromJson(Map<String, dynamic> json) {
    final params = json['params'];
    return DeviceCommandItem(
      id: json['id'] as String? ?? '',
      action: json['action'] as String? ?? '',
      params: params is Map ? Map<String, dynamic>.from(params) : const {},
      expiresAt: (json['expires_at'] as num?)?.toDouble() ?? 0,
    );
  }
}

class PauseState {
  const PauseState({required this.paused});

  final bool paused;

  factory PauseState.fromJson(Map<String, dynamic> json) {
    return PauseState(paused: json['paused'] as bool? ?? false);
  }
}

class ExecutedOption {
  const ExecutedOption({required this.status, this.commandId = ''});

  final String status;
  final String commandId;

  factory ExecutedOption.fromJson(Map<String, dynamic> json) {
    return ExecutedOption(
      status: json['status'] as String? ?? '',
      commandId: json['command_id'] as String? ?? '',
    );
  }
}

class SuiteSummary {
  const SuiteSummary({
    this.passed = 0,
    this.failed = 0,
    this.newFailures = 0,
  });

  final int passed;
  final int failed;
  final int newFailures;

  bool get green => failed == 0 && newFailures == 0;

  factory SuiteSummary.fromJson(Map<String, dynamic> json) {
    return SuiteSummary(
      passed: (json['passed'] as num?)?.toInt() ?? 0,
      failed: (json['failed'] as num?)?.toInt() ?? 0,
      newFailures: (json['new_failures'] as num?)?.toInt() ?? 0,
    );
  }
}

class MitigationSummary {
  const MitigationSummary({this.action = '', this.status = ''});

  final String action;
  final String status;

  factory MitigationSummary.fromJson(Map<String, dynamic> json) {
    return MitigationSummary(
      action: json['action'] as String? ?? '',
      status: json['status'] as String? ?? '',
    );
  }
}

class SoftwareRunResult {
  const SoftwareRunResult({
    this.prUrl = '',
    this.repo = '',
    this.suite,
    this.mitigation,
  });

  final String prUrl;
  final String repo;
  final SuiteSummary? suite;
  final MitigationSummary? mitigation;

  factory SoftwareRunResult.fromJson(Map<String, dynamic> json) {
    final suite = json['suite'];
    final mitigation = json['mitigation'];
    return SoftwareRunResult(
      prUrl: json['pr_url'] as String? ?? '',
      repo: json['repo'] as String? ?? '',
      suite: suite is Map
          ? SuiteSummary.fromJson(Map<String, dynamic>.from(suite))
          : null,
      mitigation: mitigation is Map
          ? MitigationSummary.fromJson(Map<String, dynamic>.from(mitigation))
          : null,
    );
  }
}
