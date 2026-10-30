/// Saved pairing: where the API lives and how this device signs decisions.
/// `token` is a per-user device token (`ta_dev_…`, §8.4) or the legacy
/// self-hosted mobile token; `orgId` is set by the claim flow.
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
  bool get isDeviceToken => token.startsWith('ta_dev_');

  Uri get wsUri {
    final base = Uri.parse(apiUrl);
    final scheme = base.scheme == 'https' ? 'wss' : 'ws';
    return base.replace(scheme: scheme, path: '/api/ws');
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
