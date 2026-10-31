import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/connection.dart';

/// Pairing secrets live in the platform keystore, never in prefs or logs.
class PairingStorage {
  PairingStorage({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _apiUrlKey = 'api_url';
  static const _tokenKey = 'mobile_token';
  static const _deviceKey = 'device_name';
  static const _orgKey = 'org_id';

  Future<Connection?> load() async {
    final values = await _storage.readAll();
    final apiUrl = values[_apiUrlKey];
    if (apiUrl == null || apiUrl.isEmpty) return null;
    return Connection(
      apiUrl: apiUrl,
      token: values[_tokenKey] ?? '',
      deviceName: values[_deviceKey] ?? 'phone',
      orgId: values[_orgKey] ?? '',
    );
  }

  Future<void> save(Connection connection) async {
    await _storage.write(key: _apiUrlKey, value: connection.apiUrl);
    await _storage.write(key: _tokenKey, value: connection.token);
    await _storage.write(key: _deviceKey, value: connection.deviceName);
    await _storage.write(key: _orgKey, value: connection.orgId);
  }

  Future<void> clear() async {
    try {
      await _storage.deleteAll();
    } catch (_) {
      for (final key in [_apiUrlKey, _tokenKey, _deviceKey, _orgKey]) {
        await _storage.delete(key: key);
      }
    }
  }
}
