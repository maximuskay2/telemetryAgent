import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/connection.dart';
import '../models/pending_action.dart';
import '../models/production.dart';
import '../models/run_report.dart';

/// Thin REST client for the agent API. Throws [ApiError] on failures.
class AgentApi {
  AgentApi({required this.connection, http.Client? client})
      : _client = client ?? http.Client();

  final Connection connection;
  final http.Client _client;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (connection.token.isNotEmpty) 'X-Mobile-Token': connection.token,
      };

  Uri _uri(String path) =>
      Uri.parse(connection.apiUrl).replace(path: path);

  /// Server's `{"detail": ...}` message, so 400s explain themselves
  /// (for example why a hard limit can't be marked normal).
  static String _detailOf(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map) {
        final detail = decoded['detail'] ?? decoded['message'];
        if (detail is String && detail.isNotEmpty) return detail;
      }
    } catch (_) {
      // Fall through to the generic message.
    }
    return 'Bad request.';
  }

  Future<bool> checkHealth() async {
    try {
      final response = await _client
          .get(_uri('/api/health'))
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<List<PendingAction>> openActions() async {
    final body = await _getJson('/api/actions') as Map<String, dynamic>;
    final open = body['open'];
    if (open is! List) return const [];
    return open
        .whereType<Map>()
        .map((a) => PendingAction.fromJson(Map<String, dynamic>.from(a)))
        .toList();
  }

  Future<List<RunReport>> runs() async {
    final body = await _getJson('/api/runs') as Map<String, dynamic>;
    final runs = body['runs'];
    if (runs is! List) return const [];
    return runs
        .whereType<Map>()
        .map((r) => RunReport.fromListJson(Map<String, dynamic>.from(r)))
        .toList();
  }

  Future<RunReport> runDetail(String runId) async {
    final body = await _getJson('/api/runs/$runId');
    return RunReport.fromDetailJson(Map<String, dynamic>.from(body as Map));
  }

  /// Monitored systems (for feed card names + profile bands).
  Future<List<SystemSummary>> systems() async {
    final body = await _getJson('/api/systems') as Map<String, dynamic>;
    final systems = body['systems'];
    if (systems is! List) return const [];
    return systems
        .whereType<Map>()
        .map((s) => SystemSummary.fromJson(Map<String, dynamic>.from(s)))
        .toList();
  }

  /// A system's profile (normal ranges feed the temperature band).
  Future<Map<String, dynamic>> profile(String systemId) async {
    final body =
        await _getJson('/api/systems/$systemId/profile') as Map<String, dynamic>;
    final profile = body['profile'];
    return profile is Map ? Map<String, dynamic>.from(profile) : const {};
  }

  Future<PendingAction> decide(String runId, bool approve,
      {bool markNormal = false}) async {
    final verb = approve ? 'approve' : 'disapprove';
    final response = await _client
        .post(
          _uri('/api/actions/$runId/$verb'),
          headers: _headers,
          body: jsonEncode({
            'device': connection.deviceName,
            if (!approve && markNormal) 'mark_normal': true,
          }),
        )
        .timeout(const Duration(seconds: 10));
    if (response.statusCode == 401) {
      throw const ApiError('Bad mobile token — re-pair this device.');
    }
    if (response.statusCode == 400) {
      throw ApiError(_detailOf(response.body));
    }
    if (response.statusCode == 404) {
      throw const ApiError('That window is gone — the run may be over.');
    }
    if (response.statusCode == 409) {
      throw const ApiError('Too late — the server already decided.');
    }
    if (response.statusCode != 200) {
      throw ApiError('Decision failed (${response.statusCode}).');
    }
    return PendingAction.fromJson(
        Map<String, dynamic>.from(jsonDecode(response.body) as Map));
  }

  /// Production fix options for one incident (§3.4).
  Future<IncidentOptions> incidentOptions(String runId) async {
    final body =
        await _getJson('/api/incidents/$runId/options') as Map<String, dynamic>;
    return IncidentOptions.fromJson(body);
  }

  /// Execute one option; 409 carries the server's safety/paused reason.
  Future<ExecutedOption> executeOption(String runId, String optionId) async {
    final body = await _postJson(
      '/api/incidents/$runId/options/$optionId/execute',
      const {},
    ) as Map<String, dynamic>;
    return ExecutedOption.fromJson(body);
  }

  Future<bool> getPaused() async {
    final body = await _getJson('/api/actions/pause') as Map<String, dynamic>;
    return body['paused'] as bool? ?? false;
  }

  Future<bool> setPaused(bool paused) async {
    final body = await _postJson(
      '/api/actions/pause',
      {'paused': paused},
    ) as Map<String, dynamic>;
    return body['paused'] as bool? ?? false;
  }

  Future<dynamic> _postJson(String path, Map<String, dynamic> body) async {
    final response = await _client
        .post(_uri(path), headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 10));
    if (response.statusCode == 401) {
      throw const ApiError('Bad mobile token — re-pair this device.');
    }
    if (response.statusCode == 400) {
      throw ApiError(_detailOf(response.body));
    }
    if (response.statusCode == 404) {
      throw const ApiError('That one is gone — the run may be over.');
    }
    if (response.statusCode == 409) {
      throw ApiError(_detailOf(response.body));
    }
    if (response.statusCode != 200) {
      throw ApiError('Request failed (${response.statusCode}).');
    }
    return jsonDecode(response.body);
  }

  Future<dynamic> _getJson(String path) async {
    final response = await _client
        .get(_uri(path), headers: _headers)
        .timeout(const Duration(seconds: 10));
    if (response.statusCode == 401) {
      throw const ApiError('Bad mobile token — re-pair this device.');
    }
    if (response.statusCode != 200) {
      throw ApiError('Request failed (${response.statusCode}).');
    }
    return jsonDecode(response.body);
  }

  void close() => _client.close();
}

/// One monitored system from GET /api/systems.
class SystemSummary {
  const SystemSummary({
    required this.systemId,
    required this.name,
    required this.kind,
    required this.status,
  });

  final String systemId;
  final String name;
  final String kind;
  final String status;

  factory SystemSummary.fromJson(Map<String, dynamic> json) {
    return SystemSummary(
      systemId: json['system_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      kind: json['kind'] as String? ?? '',
      status: json['status'] as String? ?? '',
    );
  }
}

class ApiError implements Exception {
  const ApiError(this.message);

  final String message;

  @override
  String toString() => message;
}
