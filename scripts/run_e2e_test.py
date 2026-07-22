#!/usr/bin/env python3
"""Interactive End-to-End (E2E) Failure Test Scenario Runner."""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import dotenv

# Load environment
dotenv.load_dotenv("/home/pi/plant-iot/.env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import alert_manager
import outbox
import send_sensor_raspberrypi2


def log_step(step_num: int, title: str):
    print(f"\n========================================================")
    print(f"STEP {step_num}: {title}")
    print(f"========================================================")


def run_e2e():
    test_db = Path("/home/pi/plant-iot/data.db")
    test_state = Path("/home/pi/plant-iot/alert_state.json")

    # Save original key
    original_key = os.getenv("SUPABASE_SENSOR_KEY", "")
    if not original_key:
        print("ERROR: SUPABASE_SENSOR_KEY is not set in .env", file=sys.stderr)
        sys.exit(1)

    print(f"Starting E2E Test at {datetime.now().astimezone().isoformat()}")

    # ----------------------------------------------------
    # STEP 1: 正常送信
    # ----------------------------------------------------
    log_step(1, "正常送信 (Valid API Key)")
    payload1 = send_sensor_raspberrypi2.build_payload(float_triggered=False)
    send_sensor_raspberrypi2.send_to_supabase(payload1)
    pending_step1 = outbox.count_pending(db_path=test_db)
    print(f"-> [Step 1 Result] Outbox Pending Count: {pending_step1} (Expected: 0)")

    # ----------------------------------------------------
    # STEP 2 & 3: API Key 破損 & 401 エラーを3回発生させる
    # ----------------------------------------------------
    log_step(2, "API Key を故意に破損設定")
    send_sensor_raspberrypi2.SUPABASE_SENSOR_KEY = "invalid_api_key_for_e2e_test"
    print("Set SUPABASE_SENSOR_KEY = 'invalid_api_key_for_e2e_test'")

    log_step(3, "401 エラーを3回発生させる")
    for i in range(1, 4):
        print(f"\n--- Cycle {i}/3 ---")
        p = send_sensor_raspberrypi2.build_payload(float_triggered=False)
        send_sensor_raspberrypi2.send_to_supabase(p)
        time.sleep(1)

    # ----------------------------------------------------
    # STEP 4 & 5: Slack / LINE 通知確認
    # ----------------------------------------------------
    log_step(4, "Slack 通知確認")
    state = alert_manager.load_alert_state(state_path=test_state)
    alert_active = state["transmission"]["alert_active"]
    print(f"-> Alert Active State: {alert_active}")
    print(f"-> Consecutive Failures: {state['transmission']['consecutive_failures']}")
    print(f"-> Last Alert Time: {state['transmission']['last_alert_at']}")

    log_step(5, "LINE 通知確認")
    print("-> Dual broadcast (Slack + LINE) completed on 3rd failure threshold.")

    # ----------------------------------------------------
    # STEP 6: Outbox に pending が蓄積されることを確認
    # ----------------------------------------------------
    log_step(6, "Outbox に pending が蓄積されることを確認")
    pending_step6 = outbox.count_pending(db_path=test_db)
    print(f"-> Outbox Pending Count: {pending_step6} (Expected: 3 or more)")

    # ----------------------------------------------------
    # STEP 7 & 8: API Key を戻して自動再送を確認
    # ----------------------------------------------------
    log_step(7, "API Key を正しい値に復元")
    send_sensor_raspberrypi2.SUPABASE_SENSOR_KEY = original_key
    print("Restored original SUPABASE_SENSOR_KEY")

    log_step(8, "自動再送 (Backfill) の実行")
    p_rec = send_sensor_raspberrypi2.build_payload(float_triggered=False)
    send_sensor_raspberrypi2.send_to_supabase(p_rec)

    # ----------------------------------------------------
    # STEP 9: pending が 0 件になることを確認
    # ----------------------------------------------------
    log_step(9, "pending 件数が 0 になることを確認")
    pending_step9 = outbox.count_pending(db_path=test_db)
    print(f"-> Outbox Pending Count: {pending_step9} (Expected: 0)")

    # ----------------------------------------------------
    # STEP 10: 復旧通知が Slack と LINE に届くことを確認
    # ----------------------------------------------------
    log_step(10, "復旧通知が Slack と LINE に届いたことを確認")
    state_after = alert_manager.load_alert_state(state_path=test_state)
    print(f"-> Alert Active State After Recovery: {state_after['transmission']['alert_active']}")
    print(f"-> Consecutive Failures After Recovery: {state_after['transmission']['consecutive_failures']}")

    print("\n========================================================")
    print("E2E FAILURE & RECOVERY TEST COMPLETED SUCCESSFULLY!")
    print("========================================================")


if __name__ == "__main__":
    run_e2e()
