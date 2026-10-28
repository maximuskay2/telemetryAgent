import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/connection.dart';
import '../models/pending_action.dart';
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

  Future<PendingAction> decide(String runId, bool approve) async {
    final verb = approve ? 'approve' : 'disapprove';
    final response = await _client
        .post(
          _uri('/api/actions/$runId/$verb'),
          headers: _headers,
          body: jsonEncode({'device': connection.deviceName}),
        )
        .timeout(const Duration(seconds: 10));
    if (response.statusCode == 401) {
      throw const ApiError('Bad mobile token — re-pair this device.');
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

class ApiError implements Exception {
  const ApiError(this.message);

  final String message;

  @override
  String toString() => message;
}
