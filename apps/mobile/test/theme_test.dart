import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:telemetry_agent/providers.dart';
import 'package:telemetry_agent/screens/settings_screen.dart';
import 'package:telemetry_agent/theme.dart';

// Commercial sales-ready look: Meta-style palettes both modes, light
// default, persisted switch. Hexes mirror apps/web/app/tokens.css.

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('palettes', () {
    test('light is the gray wash with Meta blue', () {
      AppTheme.mode = ThemeMode.light;
      addTearDown(() => AppTheme.mode = ThemeMode.light);
      expect(Obsidian.bg, const Color(0xFFF0F2F5));
      expect(Obsidian.surface, const Color(0xFFFFFFFF));
      expect(Obsidian.text, const Color(0xFF050505));
      expect(Obsidian.brand, const Color(0xFF0866FF));
      expect(Obsidian.onBrand, const Color(0xFFFFFFFF));
      expect(Accents.ok, const Color(0xFF0E7A2E));
    });

    test('dark is Facebook charcoal with the same blue', () {
      AppTheme.mode = ThemeMode.dark;
      addTearDown(() => AppTheme.mode = ThemeMode.light);
      expect(Obsidian.bg, const Color(0xFF18191A));
      expect(Obsidian.surface, const Color(0xFF242526));
      expect(Obsidian.text, const Color(0xFFE4E6EB));
      expect(Obsidian.brand, const Color(0xFF0866FF));
      expect(Accents.model, const Color(0xFF2D88FF));
    });

    test('status accents follow the mode', () {
      AppTheme.mode = ThemeMode.light;
      addTearDown(() => AppTheme.mode = ThemeMode.light);
      expect(Accents.fail, Accents.crit);
      expect(Accents.ok, Obsidian.ok);
      AppTheme.mode = ThemeMode.dark;
      expect(Accents.muted, Obsidian.textMuted);
    });

    test('type is Optimistic, then Helvetica / Arial', () {
      expect(telemetryLightTheme.brightness, Brightness.light);
      expect(telemetryDarkTheme.brightness, Brightness.dark);
      for (final theme in [telemetryLightTheme, telemetryDarkTheme]) {
        final body = theme.textTheme.bodyLarge;
        expect(body?.fontFamily, 'Optimistic');
        expect(body?.fontFamilyFallback, ['Helvetica', 'Arial']);
      }
    });
  });

  group('themeModeProvider', () {
    test('defaults to light with nothing saved', () async {
      SharedPreferences.setMockInitialValues({});
      final container = ProviderContainer();
      addTearDown(container.dispose);
      expect(container.read(themeModeProvider), ThemeMode.light);
      await container.read(themeModeProvider.notifier).setMode(ThemeMode.dark);
      expect(container.read(themeModeProvider), ThemeMode.dark);
      expect(AppTheme.mode, ThemeMode.dark);
      addTearDown(() => AppTheme.mode = ThemeMode.light);
    });

    test('restores a saved dark choice', () async {
      SharedPreferences.setMockInitialValues(
          {ThemeModeNotifier.key: 'dark'});
      AppTheme.mode = ThemeMode.light;
      final container = ProviderContainer();
      addTearDown(container.dispose);
      addTearDown(() => AppTheme.mode = ThemeMode.light);
      container.read(themeModeProvider);
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      expect(container.read(themeModeProvider), ThemeMode.dark);
      expect(AppTheme.mode, ThemeMode.dark);
    });
  });

  group('settings appearance', () {
    testWidgets('dark switch flips the provider', (tester) async {
      SharedPreferences.setMockInitialValues({});
      AppTheme.mode = ThemeMode.light;
      addTearDown(() => AppTheme.mode = ThemeMode.light);
      await tester.pumpWidget(
        const ProviderScope(child: MaterialApp(home: SettingsScreen())),
      );
      await tester.pumpAndSettle();
      expect(find.text('Dark mode'), findsOneWidget);
      expect(find.text('Built with Muse Spark'), findsOneWidget);
      await tester.tap(find.byType(SwitchListTile));
      await tester.pumpAndSettle();
      final container = ProviderScope.containerOf(
        tester.element(find.byType(SettingsScreen)),
      );
      expect(container.read(themeModeProvider), ThemeMode.dark);
    });
  });
}
