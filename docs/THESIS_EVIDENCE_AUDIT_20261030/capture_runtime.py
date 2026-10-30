import subprocess, re, json, datetime, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
commands=[
 ['hostname'],
 ['git','-C','/home/pi/plant-iot','status','--short'],
 ['git','-C','/home/pi/plant-iot','rev-parse','HEAD'],
 ['systemctl','show','plant-sensor-raspberrypi2.service','plant-slack-observation.service','plant-supabase-health.timer','cloudflared-quick-tunnel.service','-p','LoadState','-p','ActiveState','-p','SubState','-p','UnitFileState','-p','FragmentPath','-p','ActiveEnterTimestamp'],
 ['systemctl','--user','show','plant-iot-moisture-logger.service','-p','ActiveState','-p','SubState','-p','ExecStart','-p','ActiveEnterTimestamp'],
 ['journalctl','--list-boots','--no-pager'],
 ['journalctl','-u','plant-sensor-raspberrypi2.service','--since','2026-07-10','--until','2026-07-23','--no-pager'],
 ['journalctl','_SYSTEMD_USER_UNIT=plant-iot-moisture-logger.service','-n','5','--no-pager'],
 ['curl','-s','-o','/dev/null','-w','%{http_code}','--max-time','10','http://localhost:8010/slack/events'],
 ['curl','-s','-o','/dev/null','-w','%{http_code}','--max-time','15','https://yujisk.github.io/plant-iot-visualization/'],
]
parts=['Captured '+datetime.datetime.now().astimezone().isoformat()]
for cmd in commands:
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        output=r.stdout+r.stderr
        output=re.sub(r'https?://[^\s\"\x27]+','[URL]',output)
        output=re.sub(r'eyJ[A-Za-z0-9_.-]+|(?:sk-|sb_secret_|xoxb-)[A-Za-z0-9_.-]+','[REDACTED]',output)
        parts.extend(['$ '+' '.join(cmd), 'exit='+str(r.returncode),output])
    except subprocess.TimeoutExpired:parts.extend(['$ '+' '.join(cmd),'TIMEOUT'])
(ROOT/'runtime_evidence.txt').write_text('\n'.join(parts))
files=['send_sensor_raspberrypi2.py','send_sensor_raspi.py','outbox.py','alert_manager.py','slack_notifier.py','supabase_health_check.py','docs/PROJECT_LOG.md','docs/NEXT_ACTIONS.md','ds18b20.py','main.py','scripts/run_e2e_test.py']
manifest={str(Path('/home/pi/plant-iot')/p):hashlib.sha256((Path('/home/pi/plant-iot')/p).read_bytes()).hexdigest() for p in files}
for p in ['/home/pi/plant-iot-moisture/moisture_logger.py','/home/pi/plant-iot-moisture/README.md','/home/pi/.config/systemd/user/plant-iot-moisture-logger.service']:
    manifest[p]=hashlib.sha256(Path(p).read_bytes()).hexdigest()
(ROOT/'source_hashes.json').write_text(json.dumps(manifest,indent=2))
print('Saved runtime_evidence.txt and source_hashes.json')
