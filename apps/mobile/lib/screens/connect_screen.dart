import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/connection.dart';
import '../providers.dart';
import 'scan_screen.dart';

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
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    _token.dispose();
    _device.dispose();
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
              labelText: 'Mobile token (blank when unset)',
            ),
            obscureText: true,
            autocorrect: false,
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
                    if (scanned != null && mounted) {
                      setState(() => _url.text = scanned);
                    }
                  },
            icon: const Icon(Icons.qr_code_scanner),
            label: const Text('Scan dashboard QR'),
          ),
        ],
      ),
    );
  }
}
