# Plant IoT Flutter App

Flutter management-support app for the Plant IoT system.

## Role

GitHub Pages is for public/simple visualization. This Flutter app is for management support and care-action logging.

sensor_logs latest row -> state card -> care action input -> care_logs

## Secrets

Use only the Supabase anon public key in this app. Do not place SUPABASE_SENSOR_KEY or a service_role key in Flutter.

Run with dart defines:

```bash
# raspi を表示
flutter run --dart-define=SUPABASE_URL=https://your-project.supabase.co --dart-define=SUPABASE_ANON_KEY=your-anon-public-key --dart-define=DEVICE_ID=raspi

# raspberrypi2 を表示
flutter run --dart-define=SUPABASE_URL=https://your-project.supabase.co --dart-define=SUPABASE_ANON_KEY=your-anon-public-key --dart-define=DEVICE_ID=raspberrypi2
```

`DEVICE_ID`で表示対象のRaspberry Piを選択する。

If this directory was not created by flutter create, run once:

```bash
cd flutter_app
flutter create .
flutter pub get
```

Then keep lib/main.dart and pubspec.yaml from this implementation.
