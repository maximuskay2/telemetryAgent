import 'package:flutter/material.dart';

// Design tokens: "Enterprise Obsidian". Source of truth is
// apps/web/app/tokens.css — the hex values below are copied from there
// (§3 of ui-roadmap.md). Keep them in sync by hand.
class Obsidian {
  static const bg = Color(0xFF09090B);
  static const surface = Color(0xFF121215);
  static const surface2 = Color(0xFF18181C);
  static const border = Color(0xFF1E1E24);
  static const text = Color(0xFFFAFAFA);
  static const textMuted = Color(0xFFA1A1AA);
  static const textFaint = Color(0xFF71717A);
  static const brand = Color(0xFF6366F1);
  static const brandCyan = Color(0xFF38BDF8);
  static const ok = Color(0xFF10B981);
  static const warn = Color(0xFFF59E0B);
  static const crit = Color(0xFFEF4444);
}

final telemetryTheme = ThemeData(
  useMaterial3: true,
  brightness: Brightness.dark,
  scaffoldBackgroundColor: Obsidian.bg,
  fontFamily: 'GeistSans',
  colorScheme: const ColorScheme.dark(
    primary: Obsidian.brandCyan,
    onPrimary: Obsidian.bg,
    secondary: Obsidian.brand,
    surface: Obsidian.surface,
    onSurface: Obsidian.text,
    error: Obsidian.crit,
    onError: Obsidian.bg,
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
      backgroundColor: Obsidian.brandCyan,
      foregroundColor: Obsidian.bg,
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
