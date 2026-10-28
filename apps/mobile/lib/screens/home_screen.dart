import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/pending_action.dart';
import '../models/run_report.dart';
import '../providers.dart';
import '../services/socket.dart';
import '../theme.dart';
import 'report_screen.dart';
import 'settings_screen.dart';

/// Home: connection indicator, open veto windows, live feed + M4 reports.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final socketState = ref.watch(socketStateProvider);
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Telemetry Agent'),
          actions: [
            SocketIndicator(state: socketState.asData?.value),
            IconButton(
              tooltip: 'Settings',
              icon: const Icon(Icons.settings),
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const SettingsScreen()),
              ),
            ),
            IconButton(
              tooltip: 'Unpair',
              icon: const Icon(Icons.link_off),
              onPressed: () =>
                  ref.read(connectionProvider.notifier).disconnect(),
            ),
          ],
          bottom: const TabBar(
            tabs: [
              Tab(text: 'Feed', icon: Icon(Icons.bolt, size: 16)),
              Tab(text: 'Reports', icon: Icon(Icons.assignment, size: 16)),
            ],
          ),
        ),
        body: const Column(
          children: [
            OpenWindowsStrip(),
            Divider(height: 1),
            Expanded(
              child: TabBarView(
                children: [
                  LiveFeedTab(),
                  ReportsTab(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class LiveFeedTab extends ConsumerWidget {
  const LiveFeedTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(feedProvider);
    if (feed.isEmpty) {
      return const Center(
        child: Text(
          'Listening for live events…\nRun the demo scenario.',
          textAlign: TextAlign.center,
        ),
      );
    }
    return ListView.builder(
      itemCount: feed.length,
      itemBuilder: (context, index) => FeedRow(item: feed[index]),
    );
  }
}

/// M4: incident list from GET /api/runs with decision filters.
class ReportsTab extends ConsumerWidget {
  const ReportsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(reportFilterProvider);
    final runs = ref.watch(runsProvider);
    return Column(
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            children: [
              for (final option in ReportFilter.values)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilterChip(
                    label: Text(option.label),
                    selected: filter == option,
                    onSelected: (_) => ref
                        .read(reportFilterProvider.notifier)
                        .set(option),
                  ),
                ),
            ],
          ),
        ),
        Expanded(
          child: runs.when(
            data: (all) {
              final visible =
                  all.where(filter.matches).toList(growable: false);
              if (visible.isEmpty) {
                return Center(
                  child: Text(
                    all.isEmpty
                        ? 'No incidents yet.\nRun the demo scenario.'
                        : 'No ${filter.label.toLowerCase()} incidents.',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Accents.muted),
                  ),
                );
              }
              return RefreshIndicator(
                onRefresh: () async => ref.invalidate(runsProvider),
                child: ListView.builder(
                  itemCount: visible.length,
                  itemBuilder: (context, index) =>
                      RunRow(report: visible[index]),
                ),
              );
            },
            loading: () =>
                const Center(child: CircularProgressIndicator()),
            error: (error, _) => Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  'Could not load incidents: $error',
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class RunRow extends StatelessWidget {
  const RunRow({super.key, required this.report});

  final RunReport report;

  @override
  Widget build(BuildContext context) {
    final passed = report.status == 'PASS';
    return Card(
      child: ListTile(
        leading: Icon(
          passed ? Icons.check_circle : Icons.error,
          color: passed ? Accents.ok : Accents.fail,
        ),
        title: Text(
          shortRunId(report.runId),
          style: const TextStyle(fontFamily: 'monospace'),
        ),
        subtitle: Text(
          '${report.domain} · ${report.decision ?? 'no window'}'
          '${report.modelUsed.isNotEmpty ? ' · ${report.modelUsed}' : ''}',
          style: const TextStyle(color: Accents.muted, fontSize: 12),
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => ReportScreen(runId: report.runId),
          ),
        ),
      ),
    );
  }
}

class SocketIndicator extends StatelessWidget {
  const SocketIndicator({super.key, required this.state});

  final SocketState? state;

  @override
  Widget build(BuildContext context) {
    final live = state == SocketState.live;
    final retrying = state == SocketState.retrying;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Row(
        children: [
          Icon(
            live
                ? Icons.bolt
                : retrying
                    ? Icons.sync
                    : Icons.bolt_outlined,
            color: live
                ? Accents.ok
                : retrying
                    ? Accents.warn
                    : Accents.muted,
          ),
          Text(
            live
                ? 'live'
                : retrying
                    ? 'retrying'
                    : '…',
            style: const TextStyle(fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class FeedRow extends StatelessWidget {
  const FeedRow({super.key, required this.item});

  final FeedItem item;

  @override
  Widget build(BuildContext context) {
    final levelColor = item.level == 'ERROR' || item.level == 'CRITICAL'
        ? Accents.fail
        : item.level == 'WARNING'
            ? Accents.warn
            : null;
    final time = item.at;
    final stamp = time == null
        ? ''
        : '${time.hour.toString().padLeft(2, '0')}:'
            '${time.minute.toString().padLeft(2, '0')}:'
            '${time.second.toString().padLeft(2, '0')} ';
    return ListTile(
      dense: true,
      title: RichText(
        text: TextSpan(
          style: Theme.of(context).textTheme.bodyMedium,
          children: [
            if (item.tag != null)
              TextSpan(
                text: '[${item.tag}] ',
                style: const TextStyle(color: Accents.model, fontSize: 12),
              ),
            TextSpan(text: item.message),
          ],
        ),
      ),
      subtitle: Text(
        '$stamp${item.source} · ${item.level}',
        style: TextStyle(color: levelColor ?? Accents.muted, fontSize: 11),
      ),
    );
  }
}

/// Open veto windows with local countdowns (tap-to-decide lands in M3).
class OpenWindowsStrip extends ConsumerWidget {
  const OpenWindowsStrip({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final open = ref.watch(openActionsProvider);
    return open.when(
      data: (actions) {
        if (actions.isEmpty) return const SizedBox.shrink();
        return Column(
          children: [
            for (final action in actions)
              _CountdownTile(
                key: ValueKey(action.runId),
                runId: action.runId,
                title: action.action,
              ),
          ],
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
    );
  }
}

class _CountdownTile extends StatefulWidget {
  const _CountdownTile({super.key, required this.runId, required this.title});

  final String runId;
  final String title;

  @override
  State<_CountdownTile> createState() => _CountdownTileState();
}

class _CountdownTileState extends State<_CountdownTile> {
  @override
  Widget build(BuildContext context) {
    return Consumer(
      builder: (context, ref, _) {
        ref.watch(clockProvider);
        final open = ref.watch(openActionsProvider).asData?.value ?? const [];
        PendingAction? action;
        for (final candidate in open) {
          if (candidate.runId == widget.runId) action = candidate;
        }
        if (action == null || !action.isOpen) {
          return const SizedBox.shrink();
        }
        final left = action.secondsLeft();
        final urgent = left <= 5;
        return Container(
          width: double.infinity,
          color: urgent ? Accents.fail.withAlpha(40) : Accents.warn.withAlpha(30),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Text(
            'VETO ${left}s · ${action.action}',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              color: urgent ? Accents.fail : Accents.warn,
            ),
          ),
        );
      },
    );
  }
}
