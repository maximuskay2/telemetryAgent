/// Saved pairing: where the API lives and how this device signs decisions.
class Connection {
  const Connection({
    required this.apiUrl,
    required this.token,
    required this.deviceName,
  });

  final String apiUrl;
  final String token;
  final String deviceName;

  Uri get wsUri {
    final base = Uri.parse(apiUrl);
    final scheme = base.scheme == 'https' ? 'wss' : 'ws';
    return base.replace(scheme: scheme, path: '/api/ws');
  }

  Connection copyWith({String? apiUrl, String? token, String? deviceName}) {
    return Connection(
      apiUrl: apiUrl ?? this.apiUrl,
      token: token ?? this.token,
      deviceName: deviceName ?? this.deviceName,
    );
  }
}
