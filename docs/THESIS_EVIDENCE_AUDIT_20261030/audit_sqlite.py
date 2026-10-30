"""Read-only evidence extraction; never imports production logger modules."""
import sqlite3, json, csv, math, statistics, hashlib, datetime as dt
from pathlib import Path
from collections import Counter
from itertools import groupby
ROOT = Path(__file__).resolve().parent
TZ = dt.timezone(dt.timedelta(hours=9))
def open_ro(path):
    c = sqlite3.connect('file:' + path + '?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    c.execute('BEGIN')
    return c
def time(r): return dt.datetime.fromisoformat(r['observed_at_utc']).astimezone(TZ)
def describe(rows):
    values = [r['adc_raw'] for r in rows if r['adc_raw'] is not None]
    gaps = [(time(b)-time(a)).total_seconds() for a,b in zip(rows,rows[1:])]
    return dict(n=len(rows), first_jst=time(rows[0]).isoformat(), last_jst=time(rows[-1]).isoformat(),
        minimum=min(values),median=statistics.median(values),maximum=max(values),mean=statistics.mean(values),
        flags=dict(Counter(r['quality_flag'] for r in rows)),null_count=len(rows)-len(values),
        min_interval_s=min(gaps) if gaps else None,median_interval_s=statistics.median(gaps) if gaps else None,
        max_interval_s=max(gaps) if gaps else None, intervals_over_90s=sum(x>90 for x in gaps))
c = open_ro('/home/pi/plant-iot-moisture/readings.sqlite3')
query = "SELECT * FROM adc_readings WHERE observed_at_utc <= '2026-10-30T08:10:00.543+00:00' ORDER BY observed_at_utc,id"
rows = [dict(r) for r in c.execute(query)]
events = [dict(r) for r in c.execute('SELECT * FROM observation_events ORDER BY id')]
schema = [dict(r) for r in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")]
c.close()
end19 = dt.datetime(2026,10,20,tzinfo=TZ)
through19 = [r for r in rows if time(r)<end19]
continuous19 = [r for r in through19 if r['id']>=2]
expected19 = math.ceil((end19-time(continuous19[0])).total_seconds()/60)
pilot_start = time(rows[1]);pilot_end=pilot_start+dt.timedelta(days=1)
pilot = [r for r in rows if pilot_start<=time(r)<pilot_end]
daily = []
for day,rs in groupby(rows, key=lambda r:time(r).date().isoformat()):
    rs=list(rs);v=[r['adc_raw'] for r in rs if r['adc_raw'] is not None]
    daily.append(dict(day_jst=day,n=len(rs),minimum=min(v),median=statistics.median(v),maximum=max(v),mean=statistics.mean(v),near_max=sum(r['adc_raw']>=4094 for r in rs if r['adc_raw'] is not None)))
gaps = sorted([dict(seconds=(time(b)-time(a)).total_seconds(),start_jst=time(a).isoformat(),end_jst=time(b).isoformat()) for a,b in zip(rows,rows[1:])],key=lambda r:r['seconds'],reverse=True)[:10]
jumps = sorted([dict(delta=b['adc_raw']-a['adc_raw'],start_jst=time(a).isoformat(),end_jst=time(b).isoformat(),before=a['adc_raw'],after=b['adc_raw']) for a,b in zip(rows,rows[1:]) if a['adc_raw'] is not None and b['adc_raw'] is not None],key=lambda r:abs(r['delta']),reverse=True)[:15]
for name,rs in [('adc_snapshot.csv',rows),('adc_daily.csv',daily)]:
    with (ROOT/name).open('w') as f:
        w=csv.DictWriter(f,fieldnames=rs[0].keys());w.writeheader();w.writerows(rs)
out=open_ro('/home/pi/plant-iot/data.db')
outquery='SELECT device_id,status,count(*) n,min(created_at) first_utc,max(created_at) last_utc,max(retry_count) retry_max,sum(retry_count>0) retried_rows FROM outbox_queue GROUP BY 1,2'
outbox=[dict(r) for r in out.execute(outquery)]
out.close()
manual=list(csv.DictReader(open('/home/pi/plant-iot-moisture/initial_pilot_49_samples.csv')))
manual_summary=[]
for phase,rs in groupby(manual,key=lambda r:r['phase']):
    rs=list(rs);v=[int(r['adc_raw']) for r in rs]
    manual_summary.append(dict(phase=phase,n=len(rs),minimum=min(v),median=statistics.median(v),maximum=max(v),mean=statistics.mean(v)))
result=dict(query=query,schema=schema,all=describe(rows),through19=describe(through19),continuous19=describe(continuous19),continuous19_expected=expected19,pilot24h=describe(pilot),events=events,daily=daily,gaps=gaps,jumps=jumps,outbox_query=outquery,outbox=outbox,manual49=manual_summary,adc_csv_sha256=hashlib.sha256((ROOT/'adc_snapshot.csv').read_bytes()).hexdigest())
(ROOT/'sqlite_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ['schema','daily','gaps','jumps']},ensure_ascii=False,indent=2))
