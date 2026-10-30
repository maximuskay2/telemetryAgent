import 'package:flutter/material.dart';

import '../models/production.dart';
import '../theme.dart';
import 'widgets.dart';

String optionStatusLabel(String status) => switch (status) {
      'available' => 'Available',
      'sent' => 'Sent…',
      'done' => 'Done ✓',
      'failed' => 'Failed',
      'expired' => 'Expired',
      'cancelled' => 'Cancelled',
      _ => status,
    };

/// Software · PR ready: summary, fail→pass proof, Open PR, and the live
/// mitigation countdown (Roll back now / Cancel). Shows "PR pending" and
/// "No mitigation" until the backend provides them.
class PrReadyCard extends StatelessWidget {
  const PrReadyCard({
    super.key,
    required this.summary,
    required this.proofLine,
    this.prUrl = '',
    required this.onOpenPr,
    this.mitigationLabel = '',
    this.mitigationDetail = '',
    this.mitigationSecondsLeft,
    required this.onMitigateNow,
    required this.onCancelMitigation,
  });

  final String summary;
  final String proofLine;
  final String prUrl;
  final void Function(String url) onOpenPr;
  final String mitigationLabel;
  final String mitigationDetail;
  final int? mitigationSecondsLeft;
  final VoidCallback onMitigateNow;
  final VoidCallback onCancelMitigation;

  @override
  Widget build(BuildContext context) {
    final hasPr = prUrl.isNotEmpty;
    final hasMitigation = mitigationLabel.isNotEmpty;
    return SectionCard(
      title: 'Software · PR ready',
      trailing: StatusBadge(hasPr ? BadgeState.verified : BadgeState.observing),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(summary, style: const TextStyle(fontSize: 14)),
          if (proofLine.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              proofLine,
              style: TextStyle(
                  color: Accents.ok,
                  fontSize: 13,
                  fontWeight: FontWeight.w600),
            ),
          ],
          const SizedBox(height: 8),
          if (hasPr)
            ElevatedButton.icon(
              onPressed: () => onOpenPr(prUrl),
              icon: const Icon(Icons.open_in_new, size: 16),
              label: const Text('Open PR'),
            )
          else
            Text('PR pending — the fix is still being proven.',
                style: TextStyle(color: Accents.muted)),
          const SizedBox(height: 8),
          if (hasMitigation) ...[
            Text(
              mitigationSecondsLeft == null
                  ? mitigationDetail
                  : '$mitigationDetail · ${mitigationSecondsLeft}s',
              style: const TextStyle(fontSize: 13),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                ElevatedButton(
                  onPressed: onMitigateNow,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Accents.warn,
                    foregroundColor: Colors.black,
                  ),
                  child: Text(mitigationLabel),
                ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: onCancelMitigation,
                  child: const Text('Cancel'),
                ),
              ],
            ),
          ] else
            Text('No mitigation proposed.',
                style: TextStyle(color: Accents.muted)),
        ],
      ),
    );
  }
}

/// Hardware · Choose a fix: remote commands, on-site checklist, and
/// technician dispatch, each with live status. Unsafe options render
/// disabled with their reason and can never be tapped.
class HardwareFixCard extends StatelessWidget {
  const HardwareFixCard({
    super.key,
    required this.title,
    this.remote = const [],
    this.manual = const [],
    this.dispatch = const [],
    required this.onExecute,
  });

  final String title;
  final List<ProdOption> remote;
  final List<ProdOption> manual;
  final List<ProdOption> dispatch;
  final void Function(String optionId) onExecute;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: 'Hardware · Choose a fix',
      trailing: const StatusBadge(BadgeState.incident),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontSize: 14)),
          const SizedBox(height: 8),
          _OptionGroup(
            label: 'Remote',
            options: remote,
            onExecute: onExecute,
          ),
          _OptionGroup(
            label: 'On-site checklist',
            options: manual,
            onExecute: onExecute,
          ),
          _OptionGroup(
            label: 'Technician',
            options: dispatch,
            onExecute: onExecute,
          ),
        ],
      ),
    );
  }
}

class _OptionGroup extends StatelessWidget {
  const _OptionGroup({
    required this.label,
    required this.options,
    required this.onExecute,
  });

  final String label;
  final List<ProdOption> options;
  final void Function(String optionId) onExecute;

  @override
  Widget build(BuildContext context) {
    if (options.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label.toUpperCase(),
            style: TextStyle(
              color: Obsidian.textFaint,
              fontSize: 10,
              letterSpacing: 1,
            ),
          ),
          const SizedBox(height: 4),
          for (final option in options)
            _OptionRow(option: option, onExecute: onExecute),
        ],
      ),
    );
  }
}

class _OptionRow extends StatelessWidget {
  const _OptionRow({required this.option, required this.onExecute});

  final ProdOption option;
  final void Function(String optionId) onExecute;

  @override
  Widget build(BuildContext context) {
    final executable = option.executable;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  option.title,
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: executable
                        ? Obsidian.text
                        : Obsidian.textFaint,
                  ),
                ),
                if (option.detail.isNotEmpty)
                  Text(
                    option.detail,
                    style: TextStyle(
                        color: Accents.muted, fontSize: 12),
                  ),
                if (!option.safety.ok && option.safety.reason.isNotEmpty)
                  Text(
                    'Disabled: ${option.safety.reason}',
                    style: TextStyle(
                        color: Accents.fail, fontSize: 12),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          if (executable)
            OutlinedButton(
              onPressed: () => onExecute(option.id),
              child: const Text('Send'),
            )
          else
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                optionStatusLabel(option.status),
                style: TextStyle(
                    color: Accents.muted, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }
}

/// Quiet channel: nothing needs the user right now.
class WatchingCard extends StatelessWidget {
  const WatchingCard({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: 'Watching',
      trailing: const StatusBadge(BadgeState.observing),
      child: Text(
        message,
        style: TextStyle(color: Accents.muted),
      ),
    );
  }
}

/// Home-screen kill switch. Hidden banner when running, warn banner paused.
class PauseAllTile extends StatelessWidget {
  const PauseAllTile({
    super.key,
    required this.paused,
    required this.onChanged,
  });

  final bool paused;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SwitchListTile(
          title: const Text('Pause all actions'),
          subtitle: Text(
            'Stops every automatic mitigation and device command.',
            style: TextStyle(color: Accents.muted, fontSize: 12),
          ),
          value: paused,
          activeThumbColor: Accents.warn,
          onChanged: onChanged,
        ),
        if (paused)
          Container(
            color: Accents.warn.withAlpha(40),
            padding: const EdgeInsets.symmetric(
                horizontal: 16, vertical: 10),
            child: Text(
              'Paused — no automatic actions will run.',
              style: TextStyle(
                  fontWeight: FontWeight.bold, color: Accents.warn),
            ),
          ),
      ],
    );
  }
}
