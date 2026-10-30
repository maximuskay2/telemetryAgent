import 'package:flutter/material.dart';

// Design tokens: Meta-style surfaces, both modes. Source of truth is
// apps/web/app/tokens.css — the hex values below are copied from there.
// Keep them in sync by hand.
//
// Light is the default. `Obsidian.*` / `Accents.*` resolve for the
// current AppTheme.mode at build time (non-const getters), so they must
// never appear inside `const` constructors.

/// Global color mode, owned by themeModeProvider (persisted). Widgets
/// rebuild on change, so direct palette reads update with the theme.
class AppTheme {
  static ThemeMode mode = ThemeMode.light;
  static bool get isDark => mode == ThemeMode.dark;
}

/// Facebook charcoal (dark).
class DarkColors {
  static const bg = Color(0xFF18191A);
  static const surface = Color(0xFF242526);
  static const surface2 = Color(0xFF3A3B3C);
  static const border = Color(0xFF3E4042);
  static const text = Color(0xFFE4E6EB);
  static const textMuted = Color(0xFFB0B3B8);
  static const textFaint = Color(0xFF8A8D91);
  static const brand = Color(0xFF0866FF);
  static const brandCyan = Color(0xFF2D88FF);
  static const onBrand = Color(0xFFFFFFFF);
  static const danger = Color(0xFFD61C1C);
  static const ok = Color(0xFF31A24C);
  static const warn = Color(0xFFF3CF7E);
  static const crit = Color(0xFFFF887F);
}

/// Gray wash (light, the default).
class LightColors {
  static const bg = Color(0xFFF0F2F5);
  static const surface = Color(0xFFFFFFFF);
  static const surface2 = Color(0xFFE4E6EB);
  static const border = Color(0xFFCED0D4);
  static const text = Color(0xFF050505);
  static const textMuted = Color(0xFF65676B);
  static const textFaint = Color(0xFF8A8D91);
  static const brand = Color(0xFF0866FF);
  static const brandCyan = Color(0xFF0866FF);
  static const onBrand = Color(0xFFFFFFFF);
  static const danger = Color(0xFFD61C1C);
  static const ok = Color(0xFF0E7A2E);
  static const warn = Color(0xFF8A5A00);
  static const crit = Color(0xFFD61C1C);
}

/// Mode-aware palette. Read at build time; never in `const`.
class Obsidian {
  static Color get bg => AppTheme.isDark ? DarkColors.bg : LightColors.bg;
  static Color get surface =>
      AppTheme.isDark ? DarkColors.surface : LightColors.surface;
  static Color get surface2 =>
      AppTheme.isDark ? DarkColors.surface2 : LightColors.surface2;
  static Color get border =>
      AppTheme.isDark ? DarkColors.border : LightColors.border;
  static Color get text =>
      AppTheme.isDark ? DarkColors.text : LightColors.text;
  static Color get textMuted =>
      AppTheme.isDark ? DarkColors.textMuted : LightColors.textMuted;
  static Color get textFaint =>
      AppTheme.isDark ? DarkColors.textFaint : LightColors.textFaint;
  static Color get brand =>
      AppTheme.isDark ? DarkColors.brand : LightColors.brand;
  static Color get brandCyan =>
      AppTheme.isDark ? DarkColors.brandCyan : LightColors.brandCyan;
  static Color get onBrand =>
      AppTheme.isDark ? DarkColors.onBrand : LightColors.onBrand;
  static Color get danger =>
      AppTheme.isDark ? DarkColors.danger : LightColors.danger;
  static Color get ok => AppTheme.isDark ? DarkColors.ok : LightColors.ok;
  static Color get warn =>
      AppTheme.isDark ? DarkColors.warn : LightColors.warn;
  static Color get crit =>
      AppTheme.isDark ? DarkColors.crit : LightColors.crit;
}

ThemeData _buildTheme(bool dark) {
  Color pick(Color darkColor, Color lightColor) =>
      dark ? darkColor : lightColor;
  final bg = pick(DarkColors.bg, LightColors.bg);
  final surface = pick(DarkColors.surface, LightColors.surface);
  final surface2 = pick(DarkColors.surface2, LightColors.surface2);
  final border = pick(DarkColors.border, LightColors.border);
  final text = pick(DarkColors.text, LightColors.text);
  final textMuted = pick(DarkColors.textMuted, LightColors.textMuted);
  final textFaint = pick(DarkColors.textFaint, LightColors.textFaint);
  final brand = pick(DarkColors.brand, LightColors.brand);
  final onBrand = pick(DarkColors.onBrand, LightColors.onBrand);
  final crit = pick(DarkColors.crit, LightColors.crit);
  final scheme = dark ? Brightness.dark : Brightness.light;
  return ThemeData(
    useMaterial3: true,
    brightness: scheme,
    scaffoldBackgroundColor: bg,
    // Optimistic when the OS has it, else Helvetica / Arial. Optimistic
    // is proprietary: it is never vendored (see pubspec).
    fontFamily: 'Optimistic',
    fontFamilyFallback: const ['Helvetica', 'Arial'],
    colorScheme: (dark ? const ColorScheme.dark() : const ColorScheme.light())
        .copyWith(
      primary: brand,
      onPrimary: onBrand,
      secondary: brand,
      surface: surface,
      onSurface: text,
      error: crit,
      onError: onBrand,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: surface,
      foregroundColor: text,
    ),
    cardTheme: CardThemeData(
      color: surface,
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: border),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: surface2,
      selectedColor: surface2,
      labelStyle: TextStyle(color: text, fontSize: 12),
      secondaryLabelStyle: TextStyle(color: text, fontSize: 12),
      side: BorderSide(color: border),
      shape: const StadiumBorder(),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: brand,
        foregroundColor: onBrand,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: text,
        side: BorderSide(color: border),
      ),
    ),
    textTheme: TextTheme(
      bodySmall: TextStyle(color: textMuted),
      labelSmall: TextStyle(color: textFaint, fontSize: 11),
    ),
  );
}

final telemetryLightTheme = _buildTheme(false);
final telemetryDarkTheme = _buildTheme(true);

/// Status accent colors shared by the feed and countdown (mode-aware).
class Accents {
  static Color get ok => Obsidian.ok;
  static Color get warn => Obsidian.warn;
  static Color get fail => Obsidian.crit;
  static Color get crit => Obsidian.crit;
  static Color get model => Obsidian.brandCyan;
  static Color get muted => Obsidian.textMuted;
  static Color get faint => Obsidian.textFaint;
}
