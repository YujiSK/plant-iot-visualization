#!/usr/bin/env python3
"""Read-only snapshot export of raspi2 moisture SQLite (run on raspi2, stdout=CSV).
Opens with mode=ro + PRAGMA query_only, single read transaction (WAL-consistent)."""
import csv, sqlite3, sys, datetime as dt
db = sqlite3.connect("file:/home/pi/plant-iot-moisture/readings.sqlite3?mode=ro", uri=True)
db.execute("PRAGMA query_only=ON")
db.execute("BEGIN")
w = csv.writer(sys.stdout)
w.writerow(["# snapshot_utc", dt.datetime.now(dt.timezone.utc).isoformat()])
w.writerow(["id","observed_at_utc","device_id","spi_bus","spi_device","adc_channel","adc_raw","adc_voltage_estimate_v","vref_assumed_v","quality_flag","error","phase"])
for r in db.execute("SELECT id,observed_at_utc,device_id,spi_bus,spi_device,adc_channel,adc_raw,adc_voltage_estimate_v,vref_assumed_v,quality_flag,error,phase FROM adc_readings ORDER BY id"):
    w.writerow(r)
w.writerow(["# events"])
for r in db.execute("SELECT id,noted_at_utc,note FROM observation_events ORDER BY id"):
    w.writerow(["#event",*r])
db.execute("COMMIT")
