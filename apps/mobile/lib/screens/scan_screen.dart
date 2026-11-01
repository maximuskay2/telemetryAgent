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
      // Pops the raw value: the caller parses the URL and decides
      // demo-register vs fill-URL from the demo flag.
      if (parsePairingCode(barcode.rawValue) != null) {
        _done = true;
        Navigator.of(context).pop(barcode.rawValue);
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

/// True for the demo pairing QR (`{"api": ..., "demo": true}`): scanning
/// one must register a demo device session, otherwise veto decisions
/// fail with 401 (every demo veto traces to a device).
bool isDemoPairingCode(String? raw) {
  if (raw == null) return false;
  final text = raw.trim();
  if (!text.startsWith('{')) return false;
  try {
    final decoded = jsonDecode(text);
    return decoded is Map && decoded['demo'] == true;
  } catch (_) {
    return false;
  }
}
