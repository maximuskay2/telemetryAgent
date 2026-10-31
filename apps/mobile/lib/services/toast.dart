import 'package:flutter/material.dart';

/// App-wide keys so providers can navigate and toast without a context.
final rootNavigatorKey = GlobalKey<NavigatorState>();
final rootMessengerKey = GlobalKey<ScaffoldMessengerState>();

/// Short feedback toast that survives screen swaps (pair ↔ unpair).
void showToast(String message, {bool error = false}) {
  final messenger = rootMessengerKey.currentState;
  if (messenger == null) return;
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text(message),
      backgroundColor: error ? Colors.red.shade700 : Colors.green.shade700,
      behavior: SnackBarBehavior.floating,
      duration: const Duration(seconds: 3),
    ));
}
