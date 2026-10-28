import 'package:flutter/material.dart';

/// Dark ops theme matching the Command Center dashboard.
const _bg = Color(0xFF0B1011);
const _panel = Color(0xFF111719);
const _green = Color(0xFFA5EFC0);
const _amber = Color(0xFFF3CF7E);
const _red = Color(0xFFFF887F);
const _violet = Color(0xFFC4B5FD);
const _muted = Color(0xFF8A9494);

final telemetryTheme = ThemeData(
  useMaterial3: true,
  brightness: Brightness.dark,
  scaffoldBackgroundColor: _bg,
  colorScheme: const ColorScheme.dark(
    primary: _green,
    onPrimary: _bg,
    secondary: _violet,
    surface: _panel,
    onSurface: Colors.white,
    error: _red,
  ),
  appBarTheme: const AppBarTheme(
    backgroundColor: _bg,
    foregroundColor: Colors.white,
  ),
  cardTheme: const CardThemeData(
    color: _panel,
    margin: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
  ),
  elevatedButtonTheme: ElevatedButtonThemeData(
    style: ElevatedButton.styleFrom(
      backgroundColor: _green,
      foregroundColor: _bg,
    ),
  ),
  textTheme: const TextTheme(
    bodySmall: TextStyle(color: _muted, fontFamily: 'monospace'),
  ),
);

/// Status accent colors shared by the feed and countdown.
class Accents {
  static const ok = _green;
  static const warn = _amber;
  static const fail = _red;
  static const model = _violet;
  static const muted = _muted;
}
