import 'package:flutter/material.dart';

// Design tokens: classic mint green on near-black. Source of truth is
// apps/web/app/tokens.css — the hex values below are copied from there.
// Keep them in sync by hand.
class Obsidian {
  static const bg = Color(0xFF0B0E10);
  static const surface = Color(0xFF111719);
  static const surface2 = Color(0xFF0D1314);
  static const border = Color(0xFF252D2F);
  static const text = Color(0xFFE7EEEA);
  static const textMuted = Color(0xFF879694);
  static const textFaint = Color(0xFF667371);
  static const brand = Color(0xFFA5EFC0);
  static const brandCyan = Color(0xFFA5EFC0);
  static const ok = Color(0xFFA5EFC0);
  static const warn = Color(0xFFF3CF7E);
  static const crit = Color(0xFFFF887F);
  static const ink = Color(0xFF0B1710);
}

final telemetryTheme = ThemeData(
  useMaterial3: true,
  brightness: Brightness.dark,
  scaffoldBackgroundColor: Obsidian.bg,
  fontFamily: 'GeistSans',
  colorScheme: const ColorScheme.dark(
    primary: Obsidian.brand,
    onPrimary: Obsidian.ink,
    secondary: Obsidian.brand,
    surface: Obsidian.surface,
    onSurface: Obsidian.text,
    error: Obsidian.crit,
    onError: Obsidian.ink,
  ),
  appBarTheme: const AppBarTheme(
    backgroundColor: Obsidian.bg,
    foregroundColor: Obsidian.text,
  ),
  cardTheme: CardThemeData(
    color: Obsidian.surface,
    margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(12),
      side: const BorderSide(color: Obsidian.border),
    ),
  ),
  chipTheme: const ChipThemeData(
    backgroundColor: Obsidian.surface2,
    selectedColor: Obsidian.surface2,
    labelStyle: TextStyle(color: Obsidian.text, fontSize: 12),
    secondaryLabelStyle: TextStyle(color: Obsidian.text, fontSize: 12),
    side: BorderSide(color: Obsidian.border),
    shape: StadiumBorder(),
  ),
  elevatedButtonTheme: ElevatedButtonThemeData(
    style: ElevatedButton.styleFrom(
      backgroundColor: Obsidian.brand,
      foregroundColor: Obsidian.ink,
    ),
  ),
  outlinedButtonTheme: OutlinedButtonThemeData(
    style: OutlinedButton.styleFrom(
      foregroundColor: Obsidian.text,
      side: const BorderSide(color: Obsidian.border),
    ),
  ),
  textTheme: const TextTheme(
    bodySmall: TextStyle(color: Obsidian.textMuted),
    labelSmall: TextStyle(color: Obsidian.textFaint, fontSize: 11),
  ),
);

/// Status accent colors shared by the feed and countdown.
class Accents {
  static const ok = Obsidian.ok;
  static const warn = Obsidian.warn;
  static const fail = Obsidian.crit;
  static const crit = Obsidian.crit;
  static const model = Obsidian.brandCyan;
  static const muted = Obsidian.textMuted;
  static const faint = Obsidian.textFaint;
}
