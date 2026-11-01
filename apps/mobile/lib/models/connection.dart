/// Saved pairing: where the API lives and how this device signs decisions.
/// `token` is a per-user device token (`ta_dev_…`, §8.4), a demo device
/// token (`ta_demo_…`, no account), or the legacy self-hosted mobile
/// token; `orgId` is set by the claim flow.
class Connection {
  const Connection({
    required this.apiUrl,
    required this.token,
    required this.deviceName,
    this.orgId = '',
  });

  final String apiUrl;
  final String token;
  final String deviceName;
  final String orgId;

  /// Per-user device tokens ride `Authorization: Bearer`; the legacy
  /// self-hosted token keeps the `X-Mobile-Token` header.
  bool get isDeviceToken =>
      token.startsWith('ta_dev_') || token.startsWith('ta_demo_');

  /// Demo sessions carry no org; they join the public demo channel.
  bool get isDemoToken => token.startsWith('ta_demo_');

  Uri get wsUri {
    final base = Uri.parse(apiUrl);
    final scheme = base.scheme == 'https' ? 'wss' : 'ws';
    // Device tokens identify the socket (?token=); the legacy mobile
    // token has no socket form, so it stays anonymous like before.
    final query = <String, String>{
      if (isDeviceToken) 'token': token,
      if (isDeviceToken && !isDemoToken && orgId.isNotEmpty) ...{
        'org': orgId,
        'demo': '1',
      },
    };
    return base.replace(
      scheme: scheme,
      path: '/api/ws',
      queryParameters: query.isEmpty ? null : query,
    );
  }

  Connection copyWith({
    String? apiUrl,
    String? token,
    String? deviceName,
    String? orgId,
  }) {
    return Connection(
      apiUrl: apiUrl ?? this.apiUrl,
      token: token ?? this.token,
      deviceName: deviceName ?? this.deviceName,
      orgId: orgId ?? this.orgId,
    );
  }
}
