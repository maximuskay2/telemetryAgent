import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/connection.dart';
import '../providers.dart';
import 'scan_screen.dart';

/// Token guidance under the token field: which token each setup needs
/// and exactly where to get it.
const tokenHelpLines = [
  'Demo: leave blank - the demo QR and "Try the demo" register this phone automatically.',
  "Own self-hosted server: copy MOBILE_API_TOKEN from the API machine's .env (blank works only if it is unset there).",
  "Own production server: don't type here - claim a pairing code from Your devices below.",
];

/// First-run pairing: API URL + token, by hand or by dashboard QR.
class ConnectScreen extends ConsumerStatefulWidget {
  const ConnectScreen({super.key});

  @override
  ConsumerState<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends ConsumerState<ConnectScreen> {
  final _url = TextEditingController(text: 'http://192.168.1.1:8001');
  final _token = TextEditingController();
  final _device = TextEditingController(text: 'phone');
  final _code = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    _token.dispose();
    _device.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final ok = await ref
        .read(connectionProvider.notifier)
        .saveAndConnect(Connection(
          apiUrl: _url.text.trim(),
          token: _token.text.trim(),
          deviceName:
              _device.text.trim().isEmpty ? 'phone' : _device.text.trim(),
        ));
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = ok ? null : 'No agent at that URL — same Wi-Fi? API running?';
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Pair with agent')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Text(
            'Point this phone at the agent API — same Wi-Fi, API_HOST=0.0.0.0 — '
            'or scan the dashboard Pair QR.',
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _url,
            decoration: const InputDecoration(labelText: 'API URL'),
            keyboardType: TextInputType.url,
            autocorrect: false,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _token,
            decoration: const InputDecoration(
              labelText: 'Mobile token (own self-hosted server)',
            ),
            obscureText: true,
            autocorrect: false,
          ),
          const SizedBox(height: 8),
          ...tokenHelpLines.map(
            (line) => Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                '• $line',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _device,
            decoration:
                const InputDecoration(labelText: 'This device name'),
            autocorrect: false,
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
          ],
          const SizedBox(height: 20),
          ElevatedButton(
            onPressed: _busy ? null : _connect,
            child: Text(_busy ? 'Checking…' : 'Save & connect'),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _busy
                ? null
                : () async {
                    final scanned = await Navigator.of(context).push<String>(
                      MaterialPageRoute(
                          builder: (_) => const ScanScreen()),
                    );
                    if (scanned == null || !mounted) return;
                    final url = parsePairingCode(scanned);
                    if (url == null || !mounted) return;
                    if (isDemoPairingCode(scanned)) {
                      // Demo QR: register a demo device session at once —
                      // bare-URL pairing leaves decisions failing with 401.
                      setState(() {
                        _busy = true;
                        _error = null;
                        _url.text = url;
                      });
                      final problem = await ref
                          .read(connectionProvider.notifier)
                          .demoAndConnect(
                            apiUrl: url,
                            deviceName: _device.text.trim().isEmpty
                                ? 'phone'
                                : _device.text.trim(),
                          );
                      if (!mounted) return;
                      setState(() {
                        _busy = false;
                        _error = problem;
                      });
                      return;
                    }
                    setState(() => _url.text = url);
                  },
            icon: const Icon(Icons.qr_code_scanner),
            label: const Text('Scan dashboard QR'),
          ),
          const SizedBox(height: 24),
          const Text(
            'Have a pairing code? Get one from Your devices on the web, '
            'then claim it here to sign this phone in.',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _code,
            decoration: const InputDecoration(
              labelText: 'Pairing code (123-456)',
            ),
            keyboardType: TextInputType.number,
            autocorrect: false,
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _busy
                ? null
                : () async {
                    setState(() {
                      _busy = true;
                      _error = null;
                    });
                    final problem = await ref
                        .read(connectionProvider.notifier)
                        .claimAndConnect(
                          apiUrl: _url.text.trim(),
                          code: _code.text.trim(),
                          deviceName: _device.text.trim().isEmpty
                              ? 'phone'
                              : _device.text.trim(),
                        );
                    if (!mounted) return;
                    setState(() {
                      _busy = false;
                      _error = problem;
                    });
                  },
            child: Text(_busy ? 'Claiming…' : 'Claim code & connect'),
          ),
          const SizedBox(height: 24),
          const Text(
            'No account? Pair as a demo device to watch the shared demo — '
            'your vetoes stay attributed to this phone.',
          ),
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: _busy
                ? null
                : () async {
                    setState(() {
                      _busy = true;
                      _error = null;
                    });
                    final problem = await ref
                        .read(connectionProvider.notifier)
                        .demoAndConnect(
                          apiUrl: _url.text.trim(),
                          deviceName: _device.text.trim().isEmpty
                              ? 'phone'
                              : _device.text.trim(),
                        );
                    if (!mounted) return;
                    setState(() {
                      _busy = false;
                      _error = problem;
                    });
                  },
            child: Text(_busy ? 'Pairing…' : 'Try the demo'),
          ),
        ],
      ),
    );
  }
}
