import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

const supabaseUrl = String.fromEnvironment('SUPABASE_URL');
const supabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (supabaseUrl.isEmpty || supabaseAnonKey.isEmpty) {
    runApp(const MaterialApp(home: MissingConfigPage()));
    return;
  }
  await Supabase.initialize(url: supabaseUrl, anonKey: supabaseAnonKey);
  runApp(const PlantIoTApp());
}

class MissingConfigPage extends StatelessWidget {
  const MissingConfigPage({super.key});

  @override
  Widget build(BuildContext context) => const Scaffold(
        body: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Pass SUPABASE_URL and SUPABASE_ANON_KEY with --dart-define.'),
        ),
      );
}

class PlantIoTApp extends StatelessWidget {
  const PlantIoTApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Plant IoT',
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
          useMaterial3: true,
        ),
        home: const PlantHomePage(),
      );
}

class PlantHomePage extends StatefulWidget {
  const PlantHomePage({super.key});

  @override
  State<PlantHomePage> createState() => _PlantHomePageState();
}

class _PlantHomePageState extends State<PlantHomePage> {
  final supabase = Supabase.instance.client;
  static const deviceId =
      String.fromEnvironment('DEVICE_ID', defaultValue: 'raspi');
  Map<String, dynamic>? latest;
  List<Map<String, dynamic>> careLogs = const [];
  bool loading = true;
  bool saving = false;
  String? error;

  @override
  void initState() {
    super.initState();
    loadData();
  }

  Future<void> loadData() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final latestRow = await supabase
          .from('sensor_logs')
          .select('id, temperature, humidity, pressure, solution_temperature, water_raw, water_status, light_raw, light_lux, light_status, float_switch_triggered, float_switch_state, device_id, location_id, vitality_score, message, created_at')
          .eq('device_id', deviceId)
          .order('created_at', ascending: false)
          .limit(1)
          .single();
      final logs = await supabase
          .from('care_logs')
          .select('id, action_type, note, vitality_score, message, created_at')
          .order('created_at', ascending: false)
          .limit(20);
      setState(() {
        latest = Map<String, dynamic>.from(latestRow);
        careLogs = List<Map<String, dynamic>>.from(logs);
      });
    } catch (e) {
      setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> recordAction(String actionType, {String? note}) async {
    final row = latest;
    if (row == null || saving) return;
    setState(() => saving = true);
    try {
      await supabase.from('care_logs').insert({
        'action_type': actionType,
        'note': note,
        'sensor_log_id': row['id'],
        'temperature': row['temperature'],
        'humidity': row['humidity'],
        'pressure': row['pressure'],
        'vitality_score': row['vitality_score'],
        'message': row['message'],
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(actionLabel(actionType) + 'を記録しました')),
      );
      await loadData();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('記録に失敗しました: ' + e.toString())),
      );
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> showNoteDialog(String actionType) async {
    final controller = TextEditingController();
    final note = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(actionLabel(actionType) + 'のメモ'),
        content: TextField(
          controller: controller,
          minLines: 2,
          maxLines: 4,
          decoration: const InputDecoration(
            border: OutlineInputBorder(),
            hintText: '対応内容や気づいたこと',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('キャンセル')),
          FilledButton(onPressed: () => Navigator.pop(context, controller.text.trim()), child: const Text('記録')),
        ],
      ),
    );
    if (note != null) {
      await recordAction(actionType, note: note.isEmpty ? null : note);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('植物管理'),
          actions: [IconButton(onPressed: loading ? null : loadData, icon: const Icon(Icons.refresh))],
        ),
        body: buildBody(),
      );

  Widget buildBody() {
    if (loading && latest == null) return const Center(child: CircularProgressIndicator());
    if (error != null && latest == null) {
      return Padding(padding: const EdgeInsets.all(24), child: Text(error!));
    }
    return RefreshIndicator(
      onRefresh: loadData,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          StateCard(row: latest!),
          const SizedBox(height: 16),
          ActionPanel(saving: saving, onQuick: recordAction, onMemo: showNoteDialog),
          const SizedBox(height: 16),
          CareLogList(logs: careLogs),
        ],
      ),
    );
  }
}

class StateCard extends StatelessWidget {
  const StateCard({super.key, required this.row});
  final Map<String, dynamic> row;

  @override
  Widget build(BuildContext context) {
    final score = asInt(row['vitality_score']);
    final color = statusColor(score);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('最新状態', style: Theme.of(context).textTheme.titleLarge),
                Chip(label: Text(statusLabel(score)), backgroundColor: color.withOpacity(0.14)),
              ],
            ),
            const SizedBox(height: 12),
            Text(score.toString(), style: Theme.of(context).textTheme.displayLarge?.copyWith(color: color, fontWeight: FontWeight.bold)),
            Text(row['message']?.toString() ?? '状態不明'),
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                Metric(label: '温度', value: fmt(row['temperature']) + ' ℃'),
                Metric(label: '湿度', value: fmt(row['humidity']) + ' %'),
                Metric(label: '養液温度', value: fmt(row['solution_temperature']) + ' ℃'),
                Metric(
                  label: '水位',
                  value: sensorStatusLabel(
                    'water',
                    row['water_status'] ??
                        (row['float_switch_triggered'] == null
                            ? null
                            : row['float_switch_triggered'] == true
                                ? 'dry'
                                : 'enough_water'),
                  ),
                  detail: row['float_switch_state'] != null
                      ? 'float: ' + row['float_switch_state'].toString()
                      : 'raw: ' + fmtRaw(row['water_raw']),
                ),
                Metric(
                  label: '照度',
                  value: sensorStatusLabel('light', row['light_status']),
                  detail: row['light_lux'] != null
                      ? fmt(row['light_lux']) + ' lx'
                      : 'raw: ' + fmtRaw(row['light_raw']),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text('最終更新: ' + formatTime(row['created_at'])),
          ],
        ),
      ),
    );
  }
}

class Metric extends StatelessWidget {
  const Metric({super.key, required this.label, required this.value, this.detail});
  final String label;
  final String value;
  final String? detail;

  @override
  Widget build(BuildContext context) => Container(
        width: 118,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          border: Border.all(color: Theme.of(context).dividerColor),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: Theme.of(context).textTheme.labelMedium),
          const SizedBox(height: 4),
          Text(value, style: Theme.of(context).textTheme.titleMedium),
          if (detail != null) ...[
            const SizedBox(height: 4),
            Text(detail!, style: Theme.of(context).textTheme.bodySmall),
          ],
        ]),
      );
}

class ActionPanel extends StatelessWidget {
  const ActionPanel({super.key, required this.saving, required this.onQuick, required this.onMemo});
  final bool saving;
  final Future<void> Function(String actionType, {String? note}) onQuick;
  final Future<void> Function(String actionType) onMemo;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('対応を記録', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            Wrap(spacing: 8, runSpacing: 8, children: [
              FilledButton.icon(onPressed: saving ? null : () => onMemo('watered'), icon: const Icon(Icons.water_drop), label: const Text('水やり')),
              FilledButton.tonalIcon(onPressed: saving ? null : () => onMemo('moved'), icon: const Icon(Icons.open_with), label: const Text('場所変更')),
              OutlinedButton.icon(onPressed: saving ? null : () => onQuick('checked'), icon: const Icon(Icons.check_circle_outline), label: const Text('確認のみ')),
              OutlinedButton.icon(onPressed: saving ? null : () => onMemo('memo'), icon: const Icon(Icons.note_alt_outlined), label: const Text('メモ')),
            ]),
          ]),
        ),
      );
}

class CareLogList extends StatelessWidget {
  const CareLogList({super.key, required this.logs});
  final List<Map<String, dynamic>> logs;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('対応履歴', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (logs.isEmpty)
              const Text('まだ記録がありません')
            else
              ...logs.map((log) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(actionLabel(log['action_type']?.toString() ?? '')),
                    subtitle: Text([
                      if ((log['note']?.toString() ?? '').isNotEmpty) log['note'].toString(),
                      'score: ' + (log['vitality_score']?.toString() ?? '--'),
                      log['message']?.toString() ?? '',
                      formatTime(log['created_at']),
                    ].where((value) => value.isNotEmpty).join(' / ')),
                  )),
          ]),
        ),
      );
}

String actionLabel(String actionType) => switch (actionType) {
      'watered' => '水やり',
      'moved' => '場所変更',
      'checked' => '確認のみ',
      'memo' => 'メモ',
      _ => actionType,
    };

String statusLabel(int score) {
  if (score >= 80) return '良好';
  if (score >= 60) return '注意';
  return '要対応';
}

Color statusColor(int score) {
  if (score >= 80) return Colors.green.shade700;
  if (score >= 60) return Colors.orange.shade800;
  return Colors.red.shade700;
}

int asInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

String fmt(dynamic value) {
  final number = value is num ? value : num.tryParse(value?.toString() ?? '');
  return number == null ? '--' : number.toStringAsFixed(1);
}

String fmtRaw(dynamic value) {
  final number = value is num ? value : num.tryParse(value?.toString() ?? '');
  return number == null ? '--' : number.toStringAsFixed(0);
}

String sensorStatusLabel(String kind, dynamic value) {
  final status = value?.toString() ?? '';
  if (kind == 'water') {
    return switch (status) {
      'dry' => '乾燥',
      'transition' => '境界',
      'wet' => '湿り',
      'enough_water' => '十分',
      _ => '不明',
    };
  }
  if (kind == 'light') {
    return switch (status) {
      'dark' => '暗い',
      'dim' => 'やや暗い',
      'bright' => '明るい',
      _ => '不明',
    };
  }
  return '不明';
}

String formatTime(dynamic value) {
  if (value == null) return '--';
  final parsed = DateTime.tryParse(value.toString());
  if (parsed == null) return value.toString();
  return DateFormat('yyyy/MM/dd HH:mm').format(parsed.toLocal());
}
