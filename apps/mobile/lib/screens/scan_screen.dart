import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

/// QR scan for pairing: accepts a raw URL or `{"api": "<url>"}`.
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  bool _done = false;

  void _onDetect(BarcodeCapture capture) {
    if (_done) return;
    for (final barcode in capture.barcodes) {
      final url = parsePairingCode(barcode.rawValue);
      if (url != null) {
        _done = true;
        Navigator.of(context).pop(url);
        return;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Pair QR')),
      body: MobileScanner(onDetect: _onDetect),
    );
  }
}

/// Pure parser (unit-tested): raw URL or `{"api": "<url>"}` JSON.
String? parsePairingCode(String? raw) {
  if (raw == null) return null;
  final text = raw.trim();
  if (text.isEmpty) return null;
  if (text.startsWith('{')) {
    try {
      final decoded = jsonDecode(text);
      final api = decoded is Map ? decoded['api'] : null;
      if (api is String && api.startsWith('http')) return api;
    } catch (_) {
      return null;
    }
    return null;
  }
  return text.startsWith('http') ? text : null;
}
