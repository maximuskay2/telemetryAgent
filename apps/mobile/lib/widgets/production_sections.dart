import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/production.dart';
import '../models/run_report.dart';
import '../providers.dart';
import '../services/api.dart';
import '../theme.dart';
import 'action_cards.dart';
import 'widgets.dart';

/// Home-screen kill switch, wired to the pause API + actions_paused events.
class PauseSection extends ConsumerWidget {
  const PauseSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final paused = ref.watch(pauseProvider).asData?.value ?? false;
    return PauseAllTile(
      paused: paused,
      onChanged: (value) =>
          ref.read(pauseProvider.notifier).setPaused(value),
    );
  }
}

String _summary(RunReport report) {
  for (final step in report.steps) {
    if (step.step == 'diagnose' && step.detail.isNotEmpty) {
      return step.detail.split('\n').first.trim();
    }
  }
  return 'Production incident ${report.runId}';
}

String _proofLine(RunReport report) {
  final suite = report.result['suite'];
  if (suite is Map) {
    final map = Map<String, dynamic>.from(suite);
    final passed = (map['passed'] as num?)?.toInt() ?? 0;
    final failed = (map['failed'] as num?)?.toInt() ?? 0;
    final fresh = (map['new_failures'] as num?)?.toInt() ?? 0;
    final green = failed == 0 && fresh == 0;
    return 'fails → passes, '
        'suite ${green ? 'green' : 'has failures'} ($passed passed)';
  }
  return report.verifyLine;
}

void _complain(BuildContext context, Object error) {
  final message = error is ApiError ? error.message : error.toString();
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(message)),
  );
}

/// Software · PR ready, wired to live options + the veto window.
/// An empty options list renders the "PR pending" / "No mitigation"
/// states (R-6), so the card works before and after J-R4.
class SoftwarePrSection extends ConsumerWidget {
  const SoftwarePrSection({
    super.key,
    required this.report,
    required this.onOpenPr,
  });

  final RunReport report;
  final void Function(String url) onOpenPr;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final options =
        ref.watch(incidentOptionsProvider(report.runId)).asData?.value;
    final prUrl = report.result['pr_url'] as String? ?? '';

    var mitigationLabel = '';
    var mitigationDetail = '';
    var mitigationId = '';
    if (options != null) {
      for (final option in options.options) {
        if (option.kind == 'rollback' || option.kind == 'restart') {
          mitigationLabel = option.kind == 'rollback'
              ? 'Roll back now'
              : 'Restart now';
          mitigationDetail = option.title;
          mitigationId = option.id;
          break;
        }
      }
    }
    if (mitigationId.isEmpty) {
      return PrReadyCard(
        summary: _summary(report),
        proofLine: _proofLine(report),
        prUrl: prUrl,
        onOpenPr: onOpenPr,
        onMitigateNow: () {},
        onCancelMitigation: () => _cancel(ref, context),
      );
    }
    return _LiveMitigation(
      report: report,
      onOpenPr: onOpenPr,
      mitigationLabel: mitigationLabel,
      mitigationDetail: mitigationDetail,
      mitigationId: mitigationId,
    );
  }

  Future<void> _cancel(WidgetRef ref, BuildContext context) async {
    final api = ref.read(apiProvider);
    if (api == null) return;
    try {
      await api.decide(report.runId, false);
      ref.invalidate(openActionsProvider);
    } catch (error) {
      if (context.mounted) _complain(context, error);
    }
  }
}

/// Mitigation card with a live countdown. Owns a one-second timer (not the
/// shared clock stream) so disposal in tests leaves nothing pending.
class _LiveMitigation extends ConsumerStatefulWidget {
  const _LiveMitigation({
    required this.report,
    required this.onOpenPr,
    required this.mitigationLabel,
    required this.mitigationDetail,
    required this.mitigationId,
  });

  final RunReport report;
  final void Function(String url) onOpenPr;
  final String mitigationLabel;
  final String mitigationDetail;
  final String mitigationId;

  @override
  ConsumerState<_LiveMitigation> createState() => _LiveMitigationState();
}

class _LiveMitigationState extends ConsumerState<_LiveMitigation> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => setState(() {}),
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final open =
        ref.watch(openActionsProvider).asData?.value ?? const [];
    int? secondsLeft;
    for (final action in open) {
      if (action.runId == widget.report.runId &&
          action.isOpen &&
          action.ready) {
        secondsLeft = action.secondsLeft();
      }
    }
    return PrReadyCard(
      summary: _summary(widget.report),
      proofLine: _proofLine(widget.report),
      prUrl: widget.report.result['pr_url'] as String? ?? '',
      onOpenPr: widget.onOpenPr,
      mitigationLabel: widget.mitigationLabel,
      mitigationDetail: widget.mitigationDetail,
      mitigationSecondsLeft: secondsLeft,
      onMitigateNow: () => _execute(widget.mitigationId),
      onCancelMitigation: () => _cancel(),
    );
  }

  Future<void> _execute(String optionId) async {
    final api = ref.read(apiProvider);
    if (api == null) return;
    try {
      await api.executeOption(widget.report.runId, optionId);
      ref.invalidate(incidentOptionsProvider(widget.report.runId));
    } catch (error) {
      if (mounted) _complain(context, error);
    }
  }

  Future<void> _cancel() async {
    final api = ref.read(apiProvider);
    if (api == null) return;
    try {
      await api.decide(widget.report.runId, false);
      ref.invalidate(openActionsProvider);
    } catch (error) {
      if (mounted) _complain(context, error);
    }
  }
}

/// Hardware · Choose a fix, wired to live options + option_status events.
class HardwareOptionsSection extends ConsumerWidget {
  const HardwareOptionsSection({super.key, required this.report});

  final RunReport report;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final options = ref.watch(incidentOptionsProvider(report.runId));
    return options.when(
      data: (result) {
        final remote = <ProdOption>[];
        final manual = <ProdOption>[];
        final dispatch = <ProdOption>[];
        for (final option in result.options) {
          switch (option.kind) {
            case 'remote':
              remote.add(option);
            case 'manual':
              manual.add(option);
            case 'dispatch':
              dispatch.add(option);
            default:
              manual.add(option);
          }
        }
        if (result.options.isEmpty) {
          return SectionCard(
            title: 'Hardware · Choose a fix',
            child: Text(
              'No fix options yet.',
              style: TextStyle(color: Accents.muted),
            ),
          );
        }
        return HardwareFixCard(
          title: 'Appliance incident · run ${report.runId}',
          remote: remote,
          manual: manual,
          dispatch: dispatch,
          onExecute: (id) => _execute(ref, context, id),
        );
      },
      loading: () => SectionCard(
        title: 'Hardware · Choose a fix',
        child: Text(
          'Loading fix options…',
          style: TextStyle(color: Accents.muted),
        ),
      ),
      error: (error, _) => SectionCard(
        title: 'Hardware · Choose a fix',
        child: Text(
          'Could not load options: $error',
          style: TextStyle(color: Accents.muted),
        ),
      ),
    );
  }

  Future<void> _execute(
      WidgetRef ref, BuildContext context, String optionId) async {
    final api = ref.read(apiProvider);
    if (api == null) return;
    try {
      await api.executeOption(report.runId, optionId);
      ref.invalidate(incidentOptionsProvider(report.runId));
    } catch (error) {
      if (context.mounted) _complain(context, error);
    }
  }
}
