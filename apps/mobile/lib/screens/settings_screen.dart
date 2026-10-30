import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/pending_action.dart';
import '../providers.dart';
import '../theme.dart';

/// Settings: appearance, alarm rehearsal, unpairing.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);
    final connection = ref.watch(connectionProvider).asData?.value;
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          if (connection != null) ...[
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text('This device: ${connection.deviceName}'),
              subtitle: Text(
                connection.orgId.isNotEmpty
                    ? 'Signed in to org ${connection.orgId}'
                    : 'Paired (self-hosted)',
              ),
            ),
            const Divider(),
          ],
          SwitchListTile(
            title: const Text('Dark mode'),
            subtitle: const Text('Light is the default.'),
            value: themeMode == ThemeMode.dark,
            onChanged: (dark) => ref
                .read(themeModeProvider.notifier)
                .setMode(dark ? ThemeMode.dark : ThemeMode.light),
          ),
          const SizedBox(height: 8),
          const Text(
            'Rehearse the veto alarm with a fake 20 s window. The server '
            'knows nothing about it — silence the phone to stop.',
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: () {
              final now = DateTime.now().millisecondsSinceEpoch / 1000.0;
              ref.read(alarmProvider.notifier).show(PendingAction(
                    runId: 'rehearsal',
                    domain: 'software',
                    action: 'Deploy the verified inventory patch to the shop',
                    openedAt: now,
                    deadline: now + 20,
                  ));
            },
            icon: const Icon(Icons.alarm),
            label: const Text('Test alarm'),
          ),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: () async {
              await ref.read(alarmProvider.notifier).silence();
              await ref.read(connectionProvider.notifier).disconnect();
            },
            icon: const Icon(Icons.link_off),
            label: const Text('Unpair this device'),
          ),
          const SizedBox(height: 24),
          Text(
            'Built with Muse Spark',
            textAlign: TextAlign.center,
            style: TextStyle(color: Obsidian.textFaint, fontSize: 12),
          ),
        ],
      ),
    );
  }
}
