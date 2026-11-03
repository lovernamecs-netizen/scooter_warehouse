"""Reproducible synthetic ledger benchmark; reference is the deployed baseline function."""
import ast,copy,json,subprocess,time,statistics
from datetime import date,timedelta
from pathlib import Path
from server import parts
source=subprocess.check_output(['git','show','6943f73:server/parts.py']).decode('utf-8')
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='report');node.name='legacy_report';namespace=dict(vars(parts));exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'baseline','exec'),namespace);legacy=namespace['legacy_report']
days=[f'2025-12-{n:02}' for n in range(1,32)];results=[]
for total in [5000,25000,100000]:
 data=parts.initial();start=date(2021,1,1);ids=[i['id'] for i in data['items']]
 data['entries']=[{'id':'initial','kind':'STOCKTAKE','day':'2021-01-01','at':'2021-01-01T00:00:00','quantities':dict.fromkeys(ids,1000000),'scope':'START_OF_DAY'}]
 for n in range(total):
  d=(start+timedelta(days=n*1825//total)).isoformat();data['entries'].append({'id':str(n),'day':d,'at':d+'T12:00:00','kind':'VEHICLE','lines':[{'item_id':ids[n%len(ids)],'delta':-1}]})
  if n and n%1500==0:data['entries'].append({'id':'count'+str(n),'day':d,'at':d+'T10:00:00','kind':'STOCKTAKE','mode':'PARTIAL','quantities':{ids[n%len(ids)]:900000},'scope':'START_OF_DAY'})
  if n and n%997==0:data['entries'].append({'id':'cancel'+str(n),'day':d,'at':d+'T13:00:00','kind':'CANCEL','target':str(n-1)})
 timings={}
 for label in ['before','after']:
  samples=[]
  for _ in range(2):
   begin=time.perf_counter();ctx=parts.ReportContext(data) if label=='after' else None
   reports=[legacy(data,d) if label=='before' else parts.report(data,d,ctx) for d in days];samples.append(time.perf_counter()-begin)
  timings[label]=round(statistics.median(samples),4)
  if label=='before':expected=reports
  else:assert reports==expected;assert len(ctx.balances)<=3
 results.append({'ledger_events':len(data['entries']),'years':5,'month_days':31,'seconds':timings,'speedup':round(timings['before']/timings['after'],2),'all_report_fields_and_signatures_equal':True})
 print(json.dumps(results[-1]),flush=True)
path=Path(__file__).resolve().parents[2]/'purchase-sheet-results/long-term-ledger-benchmark.json';path.write_text(json.dumps(results,indent=2),encoding='utf-8')
