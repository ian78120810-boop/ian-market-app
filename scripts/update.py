"""Static dashboard updater. Standard library only; all times Asia/Taipei."""
import argparse,csv,io,json,math,re,sys,time,urllib.request,urllib.parse
from datetime import datetime,date,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'site'/'data'; START='2026-01-01'; TZ=timezone(timedelta(hours=8)); BASE='https://www.twse.com.tw/rwd/zh/'
FIELDS=['date','open','high','low','close','turnover_100m','volume','margin_pct','balance','source']
def num(x):
 try:
  n=float(str(x).replace(',','').replace('%','').strip()); return n if math.isfinite(n) else None
 except (TypeError,ValueError): return None
def iso(x):
 x=str(x).strip(); p=x.split('/')
 if len(p)==3:
  y,m,d=map(int,p);return date(y+1911 if y<1911 else y,m,d).isoformat()
 if re.fullmatch(r'\d{8}',x):return date(int(x[:4]),int(x[4:6]),int(x[6:])).isoformat()
 return date.fromisoformat(x).isoformat()
def fetch(path,d,**args):
 url=BASE+path+'?'+urllib.parse.urlencode({'date':d.replace('-',''),'response':'json',**args})
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 TaiwanMarketDashboard','Accept':'application/json'})
  with urllib.request.urlopen(req,timeout=35) as r: obj=json.load(r)
  if not isinstance(obj,dict):raise ValueError('回傳非 JSON 物件')
  returned=str(obj.get('date','')).replace('-','')
  if len(returned)==8 and returned.isdigit():
   target=d.replace('-',''); monthly=path.endswith(('HIST','FMTQIK'))
   if (returned[:6]!=target[:6] if monthly else returned!=target):raise ValueError('來源日期不符')
  elif not path.endswith(('HIST','FMTQIK')):
   # Date-specific endpoint must identify the requested date in date/title fields.
   titles=' '.join(str(t.get('title','')) for t in [obj]+obj.get('tables',[]))
   day=date.fromisoformat(d); roc=day.year-1911
   if not any(s in titles for s in [f'{roc}年{day.month:02d}月{day.day:02d}日',f'{roc}年{day.month}月{day.day}日',d,d.replace('-','')]):raise ValueError('無法確認來源交易日期')
  return obj
 finally:time.sleep(4)
def table(obj,*must):
 for t in [obj]+obj.get('tables',[]):
  fs=[re.sub(r'\s+','',str(x)) for x in t.get('fields',[])]
  if all(any(k in f for f in fs) for k in must) and t.get('data'):return fs,t['data']
 raise ValueError('缺少欄位：'+','.join(must))
def ix(fs,k):return next(i for i,f in enumerate(fs) if k in f)
def months(first,last):
 day=date.fromisoformat(first).replace(day=1)
 while day<=date.fromisoformat(last):
  yield day.isoformat();day=(day.replace(day=28)+timedelta(days=4)).replace(day=1)
def market_month(m,end):
 f,a=table(fetch('TAIEX/MI_5MINS_HIST',m),'日期','開盤指數','最高指數','最低指數','收盤指數')
 try: obj=fetch('afterTrading/FMTQIK',m);g,b=table(obj,'日期','成交金額','成交股數','發行量加權股價指數')
 except Exception: g,b=table(fetch('exchangeReport/FMTQIK',m),'日期','成交金額','成交股數','發行量加權股價指數')
 vol={iso(r[ix(g,'日期')]):[num(r[ix(g,k)]) for k in ['成交金額','成交股數','發行量加權股價指數']] for r in b};out=[]
 for r in a:
  d=iso(r[ix(f,'日期')]);o,h,l,c=[num(r[ix(f,k)]) for k in ['開盤指數','最高指數','最低指數','收盤指數']];v,q,cc=vol.get(d,[None]*3)
  if START<=d<=end and all(x is not None for x in [o,h,l,c,v,q,cc]) and l<=min(o,c)<=max(o,c)<=h and abs(c-cc)<.02 and v>=0 and q>=0:
   out.append(dict(date=d,open=o,high=h,low=l,close=c,turnover_100m=round(v/1e8,4),volume=q))
 if not out:raise ValueError('沒有可交叉驗證的交易日')
 expected={d for d in vol if START<=d<=end}
 if {r['date'] for r in out}!=expected:raise ValueError('日 K 和成交資料日期不一致')
 return out
def quote_map(day):
 f,rows=table(fetch('afterTrading/MI_INDEX',day,type='ALLBUT0999'),'證券代號','收盤價')
 return {str(r[ix(f,'證券代號')]).strip():v for r in rows if (v:=num(r[ix(f,'收盤價')])) is not None and v>0}
def margin_input(obj):
 f,rs=table(obj,'代號','今日餘額');si=ix(f,'今日餘額');ci=ix(f,'代號');shares={str(r[ci]).strip():v for r in rs if (v:=num(r[si])) is not None and v>0}
 g,rr=table(obj,'項目','今日餘額');amount=next((num(r[ix(g,'今日餘額')]) for r in rr if '融資金額' in str(r[ix(g,'項目')])),None)
 total=next((num(r[ix(g,'今日餘額')]) for r in rr if '融資' in str(r[ix(g,'項目')]) and '交易單位' in str(r[ix(g,'項目')])),None)
 if not shares or not amount or not total or abs(sum(shares.values())-total)>max(1,total*.001):raise ValueError('融資明細與統計總數不符或未公布')
 return shares,amount
def estimate(shares,amount,quotes):
 missing=set(shares)-set(quotes)
 if missing:raise ValueError(f'{len(missing)} 檔缺少收盤價；不估算')
 ratio=sum(shares[k]*quotes[k] for k in shares)/amount*100
 if not 50<ratio<500:raise ValueError('估算超出合理檢查範圍')
 return round(ratio,2)
def atomic(path,text):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text,encoding='utf-8');tmp.replace(path)
def write(state):
 atomic(DATA/'market.json',json.dumps(state,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
 buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=FIELDS,extrasaction='ignore');w.writeheader();w.writerows(state['daily']);atomic(DATA/'daily.csv','\ufeff'+buf.getvalue())
def run(full=False):
 state=json.loads((DATA/'market.json').read_text());daily={r['date']:r for r in state['daily']};errors=[];t=datetime.now(TZ);end=(t.date() if t.hour>=18 else t.date()-timedelta(days=1)).isoformat(); complete=set(state.get('complete_months',[]));current=end[:7]; pending=[m for m in months(START,end) if m[:7] not in complete or m[:7]==current or m[:7]==(date.fromisoformat(end).replace(day=1)-timedelta(days=1)).strftime('%Y-%m')]
 for m in pending:
  try:
   rows=market_month(m,end)
   for r in rows:daily[r['date']]={**daily.get(r['date'],{}),**r}
   if m[:7]!=current:complete.add(m[:7])
   print(m,'price',len(rows),flush=True)
  except Exception as e:errors.append(m+': '+str(e));print(errors[-1],flush=True)
 # Always retry the latest three sessions; backfill gradually on subsequent runs.
 dates=sorted(daily,reverse=True); recent=dates[:3];missing=[d for d in dates if d not in recent and daily[d].get('margin_pct') is None];queue=recent+missing[:(240 if full else 8)]
 cache={}
 for i,d in enumerate(queue):
  try:
   shares,amount=margin_input(fetch('marginTrading/MI_MARGN',d,selectType='ALL'))
   daily[d]['balance']=round(amount/100000,4)
   quotes=cache.get(d) or quote_map(d);cache[d]=quotes
   # A suspended or untraded issue may have no same-day close. Use earlier closes only, explicitly labeled.
   merged=dict(quotes);used_prior=False
   if set(shares)-set(merged):
    for old in [x for x in dates if x<d][:5]:
     if old not in cache:
      try:cache[old]=quote_map(old)
      except Exception:continue
     for k in set(shares)-set(merged):
      if k in cache[old]:merged[k]=cache[old][k];used_prior=True
     if not set(shares)-set(merged):break
   daily[d].update(margin_pct=estimate(shares,amount,merged),source='TWSE 估算'+('（含前收）' if used_prior else ''))
   print(d,'margin',daily[d]['margin_pct'],flush=True)
  except Exception as e:errors.append(d+': '+str(e));print(errors[-1],flush=True)
  # Persist partial progress even if later dates fail.
  if (i+1)%8==0:
   state.update(daily=[daily[k] for k in sorted(daily)],complete_months=sorted(complete),status={'message':'歷史補齊中','last_attempt':t.isoformat(),'errors':errors});write(state)
 state.update(daily=[daily[k] for k in sorted(daily)],complete_months=sorted(complete),status={'message':'部分更新／請查看紀錄' if errors else '資料更新完成','last_attempt':t.isoformat(),'errors':errors,'missing_margin':sum(r.get('margin_pct') is None for r in daily.values())});write(state)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--full',action='store_true');args=p.parse_args();run(args.full)
