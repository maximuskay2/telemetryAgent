import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/pending_action.dart';
import '../providers.dart';

/// Settings: rehearse the alarm before recording, or unpair the device.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
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
        ],
      ),
    );
  }
}
