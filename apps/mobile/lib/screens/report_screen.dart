import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/agent_step.dart';
import '../models/pending_action.dart';
import '../models/run_report.dart';
import '../providers.dart';
import '../theme.dart';
import '../widgets/production_sections.dart';
import '../widgets/widgets.dart';
import 'alarm_screen.dart' show outcomeTitle;

/// M4: one incident's Crash → Grab → Suggest → Verify → Fix story plus its
/// decision record, exactly as specced in the roadmap Screens section.
class ReportScreen extends ConsumerWidget {
  const ReportScreen({super.key, required this.runId});

  final String runId;

  Future<void> _share(RunReport report) {
    return SharePlus.instance
        .share(ShareParams(text: reportSummary(report)));
  }

  Future<void> _openPr(BuildContext context, String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null ||
        !(await canLaunchUrl(uri) &&
            await launchUrl(uri, mode: LaunchMode.externalApplication))) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not open the PR link.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(runDetailProvider(runId));
    return Scaffold(
      appBar: AppBar(
        title: Text('Report ${shortRunId(runId)}'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(runDetailProvider(runId)),
          ),
          IconButton(
            tooltip: 'Share report',
            icon: const Icon(Icons.share),
            onPressed: detail.asData == null
                ? null
                : () => _share(detail.asData!.value),
          ),
        ],
      ),
      body: detail.when(
        data: (report) => ReportBody(
          report: report,
          onOpenPr: (url) => _openPr(context, url),
        ),
        loading: () =>
            const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text('Could not load the report: $error'),
          ),
        ),
      ),
    );
  }
}

String shortRunId(String runId) =>
    runId.length > 12 ? '…${runId.substring(runId.length - 8)}' : runId;

/// Plain-text report for the system share sheet (also unit-tested).
String reportSummary(RunReport report) {
  final lines = <String>[
    'Telemetry Agent incident ${report.runId}',
    'Domain: ${report.domain} · Status: ${report.status}',
  ];
  final diagnose = stepNamed(report.steps, 'diagnose');
  if (diagnose != null && diagnose.detail.isNotEmpty) {
    lines.add('Diagnosis: ${_oneLine(diagnose.detail)}');
  }
  final suggestions = allSuggestions(report.steps);
  for (final suggestion in suggestions.take(3)) {
    lines.add('• $suggestion');
  }
  final decision = report.decisionDetail;
  if (decision != null) {
    lines.add('Decision: ${outcomeTitle(decision)}'
        '${decision.decidedBy != null ? ' by ${decision.decidedBy}' : ''}');
    if (decision.detail.isNotEmpty) lines.add(decision.detail);
  }
  final pr = report.result['pr_url'] as String?;
  if (pr != null && pr.isNotEmpty) lines.add('PR: $pr');
  final runbook = report.result['runbook'];
  if (runbook is Map && runbook['steps'] is List) {
    lines.add('Runbook: ${(runbook['steps'] as List).join(' → ')}');
  }
  return lines.join('\n');
}

AgentStep? stepNamed(List<AgentStep> steps, String name) {
  for (final step in steps) {
    if (step.step == name) return step;
  }
  return null;
}

List<String> allSuggestions(List<AgentStep> steps) {
  final seen = <String>{};
  for (final step in steps) {
    for (final suggestion in step.suggestions) {
      seen.add(suggestion);
    }
  }
  return seen.toList();
}

String _oneLine(String text) =>
    text.split('\n').first.trim().replaceAll(RegExp(r'\s+'), ' ');

class ReportBody extends StatelessWidget {
  const ReportBody({super.key, required this.report, required this.onOpenPr});

  final RunReport report;
  final void Function(String url) onOpenPr;

  @override
  Widget build(BuildContext context) {
    final passed = report.status == 'PASS';
    final noAction = report.status == 'NO_ACTION';
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 8),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    _Badge(
                      passed ? 'PASS' : report.status,
                      passed
                          ? Accents.ok
                          : noAction
                              ? Accents.muted
                              : Accents.fail,
                    ),
                    const SizedBox(width: 8),
                    _Badge(report.domain, Accents.model),
                    if (report.source.isNotEmpty) ...[
                      const SizedBox(width: 8),
                      _Badge('via ${report.source}', Accents.muted),
                    ],
                  ],
                ),
                const SizedBox(height: 10),
                SelectableText(
                  report.runId,
                  style: const TextStyle(
                      fontFamily: 'GeistMono', color: Accents.muted),
                ),
                const SizedBox(height: 4),
                Text(
                  _headerMeta(report),
                  style: const TextStyle(color: Accents.muted, fontSize: 12),
                ),
              ],
            ),
          ),
        ),
        _DecisionCard(decision: report.decisionDetail),
        _GateCard(gate: report.gate),
        _Section(
          title: 'Pipeline',
          child: _Stepper(steps: report.steps),
        ),
        ..._reportSections(),
      ],
    );
  }

  String _headerMeta(RunReport report) {
    final parts = <String>[];
    if (report.pipelineMs > 0) {
      parts.add('pipeline ${(report.pipelineMs / 1000).toStringAsFixed(1)}s');
    }
    final attempts = report.result['attempts'] as num?;
    if (attempts != null) parts.add('$attempts attempt(s)');
    final model = report.result['model_used'] as String?;
    if (model != null && model.isNotEmpty) parts.add(model);
    if (parts.isEmpty) return 'no timing info yet';
    return parts.join(' · ');
  }

  List<Widget> _reportSections() {
    final sections = <Widget>[];
    final diagnose = stepNamed(report.steps, 'diagnose');
    if (diagnose != null && diagnose.detail.isNotEmpty) {
      sections.add(_Section(
        title: 'Diagnosis',
        meta: diagnose.model,
        trailing: ProviderChip(model: diagnose.model),
        child: Text(diagnose.detail),
      ));
    }
    final suggestions = allSuggestions(report.steps);
    if (suggestions.isNotEmpty) {
      sections.add(_Section(
        title: 'Suggestions',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final suggestion in suggestions)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text('• $suggestion'),
              ),
          ],
        ),
      ));
    }
    final patch = report.result['patch_code'] as String?;
    if (patch != null && patch.isNotEmpty) {
      sections.add(_Section(
        title: 'Generated fix',
        trailing: IconButton(
          tooltip: 'Copy patch',
          icon: const Icon(Icons.copy, size: 18),
          onPressed: () => Clipboard.setData(ClipboardData(text: patch)),
        ),
        child: _CodeView(code: patch),
      ));
    }
    final runbook = report.result['runbook'];
    if (runbook is Map) {
      sections.add(_Section(
        title: 'Runbook',
        child: _RunbookView(runbook: Map<String, dynamic>.from(runbook)),
      ));
    }
    if (report.verifyLine.isNotEmpty) {
      sections.add(_Section(
        title: 'Verification evidence',
        child: Text(
          report.verifyLine,
          style: const TextStyle(
              color: Accents.ok, fontWeight: FontWeight.w600),
        ),
      ));
    }
    final verifySteps =
        report.steps.where((s) => s.step == 'verify').toList();
    if (verifySteps.isNotEmpty) {
      sections.add(_Section(
        title: 'Verification',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final step in verifySteps)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text(
                  '${step.status.isNotEmpty ? step.status : 'ran'}'
                  '${step.attempt > 0 ? ' · attempt ${step.attempt}' : ''}'
                  '${step.model.isNotEmpty ? ' · ${step.model}' : ''}'
                  '${step.detail.isNotEmpty ? '\n${step.detail}' : ''}',
                  style: const TextStyle(fontSize: 13),
                ),
              ),
          ],
        ),
      ));
    }
    sections.add(_FinalAction(
      report: report,
      onOpenPr: onOpenPr,
    ));
    if (report.domain == 'software') {
      sections.add(
          SoftwarePrSection(report: report, onOpenPr: onOpenPr));
    } else if (report.domain == 'appliance') {
      sections.add(HardwareOptionsSection(report: report));
    }
    if (report.domain == 'appliance') {
      sections.add(SectionCard(
        title: 'Sensors (live stream)',
        child: _SensorCharts(report: report),
      ));
    }
    return sections;
  }
}

class _Badge extends StatelessWidget {
  const _Badge(this.text, this.color);

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        border: Border.all(color: color.withAlpha(120)),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        text.toUpperCase(),
        style: TextStyle(color: color, fontSize: 11, letterSpacing: 1),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.child, this.meta, this.trailing});

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
                    style: const TextStyle(
                      color: Accents.muted,
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

class _DecisionCard extends StatelessWidget {
  const _DecisionCard({required this.decision});

  final PendingAction? decision;

  @override
  Widget build(BuildContext context) {
    final action = decision;
    if (action == null) {
      return const _Section(
        title: 'Decision record',
        child: Text(
          'No veto window — FAIL runs and unsafe runbooks never auto-apply.',
          style: TextStyle(color: Accents.muted),
        ),
      );
    }
    final decidedAt = action.resolvedAt;
    final when =
        decidedAt == null ? 'window open' : 'decided ${_ago(decidedAt)}';
    final byLine = [
      when,
      if ((action.decidedBy ?? '').isNotEmpty) action.decidedBy!,
      if (action.detail.isNotEmpty) action.detail,
    ].join(' · ');
    return _Section(
      title: 'Decision record',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            outcomeTitle(action),
            style: const TextStyle(
                fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 4),
          Text(
            byLine,
            style:
                const TextStyle(color: Accents.muted, fontSize: 12),
          ),
          const SizedBox(height: 4),
          Text(
            action.action,
            style: const TextStyle(fontSize: 13),
          ),
        ],
      ),
    );
  }

  String _ago(double epochSeconds) {
    final seconds = DateTime.now().millisecondsSinceEpoch ~/ 1000 -
        epochSeconds.round();
    if (seconds < 60) return '${seconds.clamp(0, 59)}s ago';
    if (seconds < 3600) return '${seconds ~/ 60}m ago';
    return '${seconds ~/ 3600}h ago';
  }
}

/// Setup gate verdict: grey when suppressed, amber when watching, red when
/// the gate escalated. Hidden for runs that never passed the gate.
class _GateCard extends StatelessWidget {
  const _GateCard({required this.gate});

  final GateDecision? gate;

  @override
  Widget build(BuildContext context) {
    final verdict = gate;
    if (verdict == null) return const SizedBox.shrink();
    final Color accent = switch (verdict.decision) {
      'suppress' => Accents.muted,
      'observe' => Accents.warn,
      'act' => Accents.fail,
      _ => Accents.muted,
    };
    return _Section(
      title: 'Gate',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Badge('Gate: ${verdict.label}', accent),
          if (verdict.reason.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              verdict.reason,
              style: const TextStyle(fontSize: 13),
            ),
          ],
          if (verdict.citation.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              'Source: ${verdict.citation}',
              style:
                  const TextStyle(color: Accents.muted, fontSize: 12),
            ),
          ],
          for (final check in verdict.checks)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                '${check.name}: ${check.result}'
                '${check.detail.isEmpty ? '' : ' — ${check.detail}'}',
                style: const TextStyle(
                    color: Accents.muted, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }
}

class _Stepper extends StatelessWidget {
  const _Stepper({required this.steps});

  final List<AgentStep> steps;

  static const _order = ['diagnose', 'generate', 'verify', 'done'];

  @override
  Widget build(BuildContext context) {
    if (steps.isEmpty) {
      return const Text('No pipeline steps streamed yet.',
          style: TextStyle(color: Accents.muted));
    }
    return Column(
      children: [
        for (final name in _order)
          if (stepNamed(steps, name) != null)
            _StepRow(step: stepNamed(steps, name)!),
      ],
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({required this.step});

  final AgentStep step;

  @override
  Widget build(BuildContext context) {
    final failed = step.status == 'FAIL' || step.status == 'error';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Icon(
            failed
                ? Icons.cancel
                : step.status == 'PASS' || step.step == 'done'
                    ? Icons.check_circle
                    : Icons.circle,
            size: 16,
            color: failed ? Accents.fail : Accents.ok,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              step.step,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          if (step.model.isNotEmpty)
            Text(step.model,
                style: const TextStyle(
                    color: Accents.model, fontSize: 11)),
          if (step.durationMs > 0) ...[
            const SizedBox(width: 8),
            Text('${step.durationMs.round()}ms',
                style: const TextStyle(
                    color: Accents.muted, fontSize: 11)),
          ],
        ],
      ),
    );
  }
}

class _CodeView extends StatelessWidget {
  const _CodeView({required this.code});

  final String code;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxHeight: 260),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.circular(6),
      ),
      child: SingleChildScrollView(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: SelectableText(
            code,
            style: const TextStyle(
                fontFamily: 'GeistMono', fontSize: 11, height: 1.5),
          ),
        ),
      ),
    );
  }
}

class _RunbookView extends StatelessWidget {
  const _RunbookView({required this.runbook});

  final Map<String, dynamic> runbook;

  @override
  Widget build(BuildContext context) {
    final steps = runbook['steps'];
    final stepList =
        steps is List ? steps.whereType<String>().toList() : const <String>[];
    final meta = <String>[];
    final target = runbook['target_temperature_c'];
    if (target is num) meta.add('hold ${target.toString()}°C');
    final delay = runbook['restart_delay_s'];
    if (delay is num) meta.add('restart delay ${delay.toInt()}s');
    final off = runbook['power_off_minutes'];
    if (off is num && off > 0) meta.add('power off ${off.toString()} min');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < stepList.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text('🛡 ${i + 1}. ${stepList[i]}'),
          ),
        if (meta.isNotEmpty)
          Text(meta.join(' · '),
              style:
                  const TextStyle(color: Accents.muted, fontSize: 12)),
        if (runbook['disables_protection'] == true)
          const Text('⚠ disables a protection — never auto-applied',
              style: TextStyle(color: Accents.fail, fontSize: 12)),
      ],
    );
  }
}

class _FinalAction extends StatelessWidget {
  const _FinalAction({required this.report, required this.onOpenPr});

  final RunReport report;
  final void Function(String url) onOpenPr;

  @override
  Widget build(BuildContext context) {
    final children = <Widget>[];
    final pr = report.result['pr_url'] as String?;
    if (pr != null && pr.isNotEmpty) {
      children.add(
        ElevatedButton.icon(
          onPressed: () => onOpenPr(pr),
          icon: const Icon(Icons.open_in_new, size: 16),
          label: const Text('Open fix PR'),
        ),
      );
    }
    final alert = report.result['alert'];
    if (alert is Map) {
      final order = alert['work_order_id'] as String?;
      final message = alert['message'] as String?;
      if (order != null && order.isNotEmpty) {
        children.add(Text('Work order: $order',
            style: const TextStyle(fontWeight: FontWeight.w600)));
      }
      if (message != null && message.isNotEmpty) {
        children.add(Text(message,
            style: const TextStyle(color: Accents.muted, fontSize: 13)));
      }
    }
    final feedback = report.result['feedback'] as String?;
    if ((feedback ?? '').isNotEmpty) {
      children.add(Text(feedback!,
          style: const TextStyle(color: Accents.fail, fontSize: 13)));
    }
    final done = stepNamed(report.steps, 'done');
    if (children.isEmpty && done != null && done.message.isNotEmpty) {
      children.add(Text(done.message));
    }
    if (children.isEmpty) {
      children.add(const Text('Nothing applied yet.',
          style: TextStyle(color: Accents.muted)));
    }
    return _Section(
      title: 'Final action',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final child in children)
            Padding(
                padding: const EdgeInsets.only(bottom: 6), child: child),
        ],
      ),
    );
  }
}

/// Swipeable temperature / current / vibration charts. The temperature
/// page shades the profile's normal band when the run carries a system.
class _SensorCharts extends ConsumerStatefulWidget {
  const _SensorCharts({required this.report});

  final RunReport report;

  @override
  ConsumerState<_SensorCharts> createState() => _SensorChartsState();
}

class _SensorChartsState extends ConsumerState<_SensorCharts> {
  int _page = 0;
  final _controller = PageController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final samples = ref.watch(fridgeTempsProvider);
    if (samples.length < 2) {
      return const Text(
        'Collecting live readings — open the fridge stream first.',
        style: TextStyle(color: Accents.muted),
      );
    }
    var systemId = widget.report.gate?.systemId ?? '';
    if (systemId.isEmpty) {
      final systems = ref.watch(systemsProvider).asData?.value ?? const [];
      for (final system in systems) {
        if (system.kind == widget.report.domain) {
          systemId = system.systemId;
          break;
        }
      }
    }
    final band = systemId.isEmpty
        ? null
        : ref.watch(profileBandProvider(systemId)).asData?.value;
    final pages = [
      _ChartPage(
        label: 'Temperature °C',
        values: [for (final s in samples) s.celsius],
        color: Accents.warn,
        band: band,
      ),
      _ChartPage(
        label: 'Current A',
        values: [for (final s in samples) s.amps],
        color: Obsidian.brandCyan,
      ),
      _ChartPage(
        label: 'Vibration g',
        values: [for (final s in samples) s.vibrationG],
        color: Accents.ok,
      ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 150,
          child: PageView(
            controller: _controller,
            onPageChanged: (page) => setState(() => _page = page),
            children: pages,
          ),
        ),
        const SizedBox(height: 4),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            for (var i = 0; i < pages.length; i++)
              Container(
                width: 6,
                height: 6,
                margin: const EdgeInsets.symmetric(horizontal: 3),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i == _page ? Accents.ok : Obsidian.textFaint,
                ),
              ),
          ],
        ),
        Text(
          '${samples.length} samples',
          style:
              const TextStyle(color: Accents.muted, fontSize: 11),
        ),
      ],
    );
  }
}

class _ChartPage extends StatelessWidget {
  const _ChartPage({
    required this.label,
    required this.values,
    required this.color,
    this.band,
  });

  final String label;
  final List<double> values;
  final Color color;
  final ({double min, double max})? band;

  @override
  Widget build(BuildContext context) {
    final spots = <FlSpot>[];
    for (var i = 0; i < values.length; i++) {
      spots.add(FlSpot(i.toDouble(), values[i]));
    }
    var minY = spots.first.y;
    var maxY = spots.first.y;
    for (final spot in spots) {
      if (spot.y < minY) minY = spot.y;
      if (spot.y > maxY) maxY = spot.y;
    }
    if (band != null) {
      if (band!.min < minY) minY = band!.min;
      if (band!.max > maxY) maxY = band!.max;
    }
    final pad = (maxY - minY).clamp(0.5, 50.0) * 0.2 + 0.2;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(
                color: Accents.muted, fontSize: 11)),
        Expanded(
          child: LineChart(
            LineChartData(
              gridData: const FlGridData(show: false),
              titlesData: const FlTitlesData(show: false),
              borderData: FlBorderData(show: false),
              minY: minY - pad,
              maxY: maxY + pad,
              lineTouchData: const LineTouchData(enabled: false),
              rangeAnnotations: RangeAnnotations(
                horizontalRangeAnnotations: [
                  if (band != null)
                    HorizontalRangeAnnotation(
                      y1: band!.min,
                      y2: band!.max,
                      color: Accents.ok.withAlpha(25),
                    ),
                ],
              ),
              lineBarsData: [
                LineChartBarData(
                  spots: spots,
                  isCurved: true,
                  color: color,
                  barWidth: 2,
                  dotData: const FlDotData(show: false),
                ),
              ],
            ),
          ),
        ),
        Text(
          'now ${values.last.toStringAsFixed(2)}',
          style:
              const TextStyle(color: Accents.muted, fontSize: 11),
        ),
      ],
    );
  }
}
