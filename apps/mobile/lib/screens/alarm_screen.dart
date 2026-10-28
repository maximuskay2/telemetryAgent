import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/pending_action.dart';
import '../providers.dart';
import '../services/api.dart';
import '../theme.dart';

/// Seconds left from the server deadline, corrected by the latest tick:
/// a fresh tick (≤2 s old) wins over the local clock.
int correctedSecondsLeft(
  PendingAction action,
  ServerTick? tick, [
  DateTime? now,
]) {
  final current = now ?? DateTime.now();
  final local = action.secondsLeft(current);
  if (tick == null || tick.runId != action.runId) return local;
  final age = current.difference(tick.at).inSeconds;
  if (age > 2) return local;
  return math.max(0, tick.left - age);
}

/// Full-screen veto: red banner, what will auto-apply, live countdown,
/// and the two decision buttons. Silencing the phone never stops the
/// server countdown — only Disapprove does that.
class AlarmRoute extends ConsumerStatefulWidget {
  const AlarmRoute({super.key, required this.action});

  final PendingAction action;

  @override
  ConsumerState<AlarmRoute> createState() => _AlarmRouteState();
}

class _AlarmRouteState extends ConsumerState<AlarmRoute> {
  bool _busy = false;
  String? _error;

  Future<void> _decide(bool approve) async {
    final api = ref.read(apiProvider);
    if (api == null || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final decided = await api.decide(widget.action.runId, approve);
      await ref.read(alarmProvider.notifier).silence();
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => OutcomeScreen(action: decided),
        ),
      );
    } on ApiError catch (error) {
      if (!mounted) return;
      if (error.message.startsWith('Too late')) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => OutcomeScreen.tooLate(action: widget.action),
          ),
        );
        return;
      }
      setState(() {
        _busy = false;
        _error = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.watch(clockProvider);
    final tick = ref.read(alarmProvider.notifier).lastTick;
    final left = correctedSecondsLeft(widget.action, tick);
    final total = math.max(
        1,
        (widget.action.deadline - widget.action.openedAt).round());
    ref.read(alarmHardwareProvider).setUrgent(left <= 5);
    return AlarmScreen(
      action: widget.action,
      secondsLeft: left,
      total: total,
      busy: _busy,
      error: _error,
      onDecide: _decide,
      onSilence: () async {
        await ref.read(alarmProvider.notifier).silence();
        if (context.mounted) Navigator.of(context).pop();
      },
    );
  }
}

class AlarmScreen extends StatelessWidget {
  const AlarmScreen({
    super.key,
    required this.action,
    required this.secondsLeft,
    required this.onDecide,
    required this.onSilence,
    this.total = 20,
    this.busy = false,
    this.error,
  });

  final PendingAction action;
  final int secondsLeft;
  final int total;
  final Future<void> Function(bool approve) onDecide;
  final Future<void> Function() onSilence;
  final bool busy;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final urgent = secondsLeft <= 5;
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              color: Accents.fail,
              padding: const EdgeInsets.symmetric(vertical: 14),
              child: const Text(
                'VETO WINDOW OPEN',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.black,
                  fontWeight: FontWeight.w900,
                  fontSize: 20,
                  letterSpacing: 2,
                ),
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  Center(
                    child: CountdownRing(
                      secondsLeft: secondsLeft,
                      total: total,
                      urgent: urgent,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'until auto-apply',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Accents.muted),
                  ),
                  const SizedBox(height: 20),
                  Text(
                    action.action,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 18),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${action.domain} · run ${action.runId}',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        color: Accents.muted, fontFamily: 'monospace'),
                  ),
                  if (error != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      error!,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Accents.fail),
                    ),
                  ],
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Expanded(
                    child: ElevatedButton(
                      onPressed:
                          busy ? null : () => onDecide(false),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Accents.fail,
                        foregroundColor: Colors.black,
                        padding: const EdgeInsets.symmetric(vertical: 18),
                      ),
                      child: Text(busy ? '…' : 'DISAPPROVE'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: busy ? null : () => onDecide(true),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Accents.ok,
                        side: const BorderSide(color: Accents.ok),
                        padding: const EdgeInsets.symmetric(vertical: 18),
                      ),
                      child: const Text('APPROVE'),
                    ),
                  ),
                ],
              ),
            ),
            TextButton(
              onPressed: busy ? null : onSilence,
              child: const Text(
                'Silence phone (server keeps counting)',
                style: TextStyle(color: Accents.muted),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Circular countdown: fraction of the server window remaining.
class CountdownRing extends StatelessWidget {
  const CountdownRing({
    super.key,
    required this.secondsLeft,
    required this.total,
    required this.urgent,
  });

  final int secondsLeft;
  final int total;
  final bool urgent;

  @override
  Widget build(BuildContext context) {
    final fraction =
        total <= 0 ? 0.0 : (secondsLeft / total).clamp(0.0, 1.0);
    final color = urgent ? Accents.fail : Colors.white;
    return SizedBox(
      width: 190,
      height: 190,
      child: CustomPaint(
        painter: _RingPainter(fraction: fraction, color: color),
        child: Center(
          child: Text(
            '${secondsLeft}s',
            style: TextStyle(
              fontSize: 64,
              fontWeight: FontWeight.w900,
              color: color,
            ),
          ),
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  const _RingPainter({required this.fraction, required this.color});

  final double fraction;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.shortestSide / 2 - 8;
    final track = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..color = const Color(0xFF2A3436);
    canvas.drawCircle(center, radius, track);
    final arc = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round
      ..color = color;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      -fraction * 2 * math.pi,
      false,
      arc,
    );
  }

  @override
  bool shouldRepaint(_RingPainter old) =>
      old.fraction != fraction || old.color != color;
}

/// Shared outcome wording (alarm outcome, reports, dashboard strip).
String outcomeTitle(PendingAction action, {bool tooLate = false}) {
  if (tooLate) return 'Too late — already applied';
  switch (action.state) {
    case 'approved':
      return 'Approved ✓';
    case 'disapproved':
      return 'Disapproved — left for a human';
    case 'auto_applied':
      return 'Auto-applied ✓';
    case 'failed':
      return 'Apply failed';
    case 'expired':
      return 'Window expired';
    case 'pending':
      return 'Veto window open';
    default:
      return action.state;
  }
}

/// Outcome after a decision: what the server did and why.
class OutcomeScreen extends StatelessWidget {
  const OutcomeScreen({super.key, required this.action})
      : tooLate = false;

  const OutcomeScreen.tooLate({super.key, required this.action})
      : tooLate = true;

  final PendingAction action;
  final bool tooLate;

  String get title => outcomeTitle(action, tooLate: tooLate);

  @override
  Widget build(BuildContext context) {
    final good = action.state == 'approved' ||
        action.state == 'auto_applied' ||
        action.state == 'disapproved';
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Icon(
                good ? Icons.check_circle : Icons.error,
                size: 72,
                color: good ? Accents.ok : Accents.fail,
              ),
              const SizedBox(height: 20),
              Text(
                title,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              Text(
                action.action,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Accents.muted),
              ),
              if (action.detail.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  action.detail,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      color: Accents.muted, fontFamily: 'monospace'),
                ),
              ],
              const SizedBox(height: 32),
              ElevatedButton(
                onPressed: () => Navigator.of(context)
                    .popUntil((route) => route.isFirst),
                child: const Text('Back to feed'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
