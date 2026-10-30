import 'package:flutter/material.dart';

import '../theme.dart';

/// Status badge following the §3 vocabulary exactly (word + color + icon).
enum BadgeState {
  verified,
  ignored,
  observing,
  incident,
  hardLimit,
  ai,
  learning,
  setupNeeded,
}

class StatusBadge extends StatelessWidget {
  const StatusBadge(this.state, {super.key, this.label});

  final BadgeState state;
  final String? label;

  (Color, IconData, String) get _parts => switch (state) {
        BadgeState.verified => (Accents.ok, Icons.check, 'Verified'),
        BadgeState.ignored => (Accents.ok, Icons.health_and_safety, 'Normal · ignored'),
        BadgeState.observing => (Accents.warn, Icons.contrast, 'Observing'),
        BadgeState.incident => (Accents.fail, Icons.report_outlined, 'Incident'),
        BadgeState.hardLimit => (Accents.fail, Icons.block, 'Hard limit'),
        BadgeState.ai => (Obsidian.brandCyan, Icons.auto_awesome, label ?? 'AI'),
        BadgeState.learning => (Obsidian.brandCyan, Icons.sync, 'Learning'),
        BadgeState.setupNeeded => (Accents.warn, Icons.settings_outlined, 'Setup needed'),
      };

  @override
  Widget build(BuildContext context) {
    final (color, icon, word) = _parts;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withAlpha(30),
        border: Border.all(color: color.withAlpha(100)),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: color),
          const SizedBox(width: 5),
          Text(
            word,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

/// Big tabular number with a small label (alarm header, report hero).
class MetricTile extends StatelessWidget {
  const MetricTile({super.key, required this.label, required this.value, this.tone});

  final String label;
  final String value;
  final Color? tone;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label.toUpperCase(),
          style: TextStyle(
            color: Obsidian.textFaint,
            fontSize: 10,
            letterSpacing: 1,
          ),
        ),
        Text(
          value,
          style: TextStyle(
            color: tone ?? Obsidian.text,
            fontSize: 20,
            fontWeight: FontWeight.w700,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
      ],
    );
  }
}

/// Compact CRASH → GRAB → SUGGEST → VERIFY/SAFETY → FIX stepper.
class StepperRow extends StatelessWidget {
  const StepperRow({super.key, required this.reached, this.appliance = false});

  /// 5 flags in CRASH, GRAB, SUGGEST, VERIFY, FIX order.
  final List<bool> reached;
  final bool appliance;

  @override
  Widget build(BuildContext context) {
    final labels = [
      'CRASH',
      'GRAB',
      'SUGGEST',
      appliance ? 'SAFETY' : 'VERIFY',
      'FIX',
    ];
    return Wrap(
      spacing: 4,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        for (var i = 0; i < labels.length; i++) ...[
          if (i > 0)
            Text('→',
                style: TextStyle(color: Obsidian.textFaint, fontSize: 10)),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
            decoration: BoxDecoration(
              color: (i < reached.length && reached[i])
                  ? Accents.ok.withAlpha(30)
                  : Obsidian.surface2,
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              labels[i],
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w700,
                color: (i < reached.length && reached[i])
                    ? Accents.ok
                    : Obsidian.textFaint,
              ),
            ),
          ),
        ],
      ],
    );
  }
}

/// Titled card section (uppercase title, optional meta + trailing action).
class SectionCard extends StatelessWidget {
  const SectionCard({
    super.key,
    required this.title,
    required this.child,
    this.meta,
    this.trailing,
  });

  final String title;
  final Widget child;
  final String? meta;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${title.toUpperCase()}${meta != null && meta!.isNotEmpty ? ' · $meta' : ''}',
                    style: TextStyle(
                      color: Obsidian.textMuted,
                      fontSize: 11,
                      letterSpacing: 1.2,
                    ),
                  ),
                ),
                trailing ?? const SizedBox.shrink(),
              ],
            ),
            const SizedBox(height: 8),
            child,
          ],
        ),
      ),
    );
  }
}

/// Model → provider chip (mirrors the web's modelProvider helper).
String providerLabel(String model) {
  final name = model.toLowerCase();
  if (name.contains('wonder')) return 'Meta · Muse Wonder';
  if (name.contains('spark')) {
    if (name.contains('baseten') || name.contains('open')) {
      return 'Baseten · Spark Open';
    }
    return 'Meta · Muse Spark';
  }
  if (name.contains('fireworks')) return 'Fireworks';
  if (name.contains('modal')) return 'Modal';
  if (name.contains('docker')) return 'Docker';
  if (name.contains('stub') || name.contains('heuristic')) {
    return 'Local heuristic';
  }
  if (name.isEmpty) return '—';
  return model;
}

class ProviderChip extends StatelessWidget {
  const ProviderChip({super.key, required this.model});

  final String model;

  @override
  Widget build(BuildContext context) {
    if (model.isEmpty) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: Obsidian.brandCyan.withAlpha(25),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        providerLabel(model),
        style: TextStyle(color: Obsidian.brandCyan, fontSize: 11),
      ),
    );
  }
}
