"""Static dashboard updater. Standard library only; all times Asia/Taipei."""
import argparse,csv,io,json,math,re,sys,time,urllib.request,urllib.parse
from datetime import datetime,date,timedelta,timezone
from pathlib import Path
import rankings, concepts
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
  if path.endswith('STOCK_DAY') and ('沒有符合' in str(obj.get('stat','')) or '查無資料' in str(obj.get('stat',''))):return obj
  returned=str(obj.get('date','')).replace('-','')
  if len(returned)==8 and returned.isdigit():
   target=d.replace('-',''); monthly=path.endswith(('HIST','FMTQIK','STOCK_DAY'))
   if (returned[:6]!=target[:6] if monthly else returned!=target):raise ValueError('來源日期不符')
  elif not path.endswith(('HIST','FMTQIK','STOCK_DAY')):
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
def quote_map(day,obj=None):
 if obj is None:obj=fetch('afterTrading/MI_INDEX',day,type='ALLBUT0999')
 result={}
 for t in [obj]+obj.get('tables',[]):
  f=[re.sub(r'\s+','',str(x)) for x in t.get('fields',[])]
  if not all(any(k in v for v in f) for k in ('證券代號','收盤價')):continue
  ci,pi=ix(f,'證券代號'),ix(f,'收盤價')
  for r in t.get('data',[]):
   v=num(r[pi]);k=str(r[ci]).strip()
   if v is not None and v>0:result[k]=v
 if not result:raise ValueError('沒有每日收盤行情')
 return result

def stock_month(code,month,cache):
 """Monthly official individual quotes; never accept future prices for a past day."""
 key=(code,month)
 if key not in cache:
  obj=fetch('afterTrading/STOCK_DAY',month,stockNo=code)
  if '沒有符合' in str(obj.get('stat','')) or '查無資料' in str(obj.get('stat','')):
   cache[key]=[]
  else:
   f,rs=table(obj,'日期','收盤價'); rows=[]
   for r in rs:
    d=iso(r[ix(f,'日期')]);v=num(r[ix(f,'收盤價')])
    if d[:7]!=month[:7]:raise ValueError('個股行情月份不符')
    if v is not None and v>0:rows.append((d,v))
   cache[key]=sorted(rows)
 return cache[key]

def resolve_price(code,day,cache,months_back=12):
 m=date.fromisoformat(day).replace(day=1)
 for _ in range(months_back+1):
  rows=stock_month(code,m.isoformat(),cache)
  valid=[(d,v) for d,v in rows if d<=day]
  if valid:return valid[-1]
  m=(m-timedelta(days=1)).replace(day=1)
 return None

def margin_input(obj):
 f,rs=table(obj,'代號','今日餘額');si=ix(f,'今日餘額');ci=ix(f,'代號');shares={str(r[ci]).strip():v for r in rs if (v:=num(r[si])) is not None and v>0}
 g,rr=table(obj,'項目','今日餘額');amount=next((num(r[ix(g,'今日餘額')]) for r in rr if '融資金額' in str(r[ix(g,'項目')])),None)
 total=next((num(r[ix(g,'今日餘額')]) for r in rr if '融資' in str(r[ix(g,'項目')]) and '交易單位' in str(r[ix(g,'項目')])),None)
 if not shares or not amount or not total or abs(sum(shares.values())-total)>max(1,total*.001):raise ValueError('融資明細與統計總數不符或未公布')
 return shares,amount
def estimate(shares,amount,quotes):
 missing=set(shares)-set(quotes)
 if missing:raise ValueError(f'{len(missing)} 檔缺少收盤價；不估算；代號：'+', '.join(sorted(missing)))
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
 dates=sorted(daily,reverse=True); recent=dates[:3];missing=[d for d in dates if d not in recent and daily[d].get('margin_pct') is None]
 ranks=state.setdefault('rankings',{});rank_missing=[d for d in dates if d not in recent and not all(k in ranks.get(d,{}) for k in ('sectors','credit'))]
 # Full mode still shares the original history queue; otherwise prioritize recent sessions and bounded backfill.
 queue=list(dict.fromkeys(recent+missing[:(50 if full else 8)]+rank_missing[:(50 if full else 8)]))
 try:companies,classification_date=rankings.company_map()
 except Exception as e:companies={};classification_date='';errors.append('排行榜產業分類：'+str(e))
 # New concept history is backfilled gradually (recent 6 sessions first).
 concept_missing=[d for d in dates[6:] if not all(k in ranks.get(d,{}).get('concepts',{}) for k in ('listed','otc')) or 'credit_otc' not in ranks.get(d,{})]
 concept_missing.sort(key=lambda d:ranks.get(d,{}).get('concept_attempt',''))
 concept_dates=set(dates[:6]+concept_missing[: (25 if full else 5)])
 queue=list(dict.fromkeys(recent+dates[:6]+[d for d in dates if d in concept_dates]+queue))
 try:otc=concepts.otc_companies()
 except Exception as e:otc={};errors.append('上櫃公司分類：'+str(e))
 cache={}; stock_cache={}
 for i,d in enumerate(queue):
  if (datetime.now(TZ)-t).total_seconds()>68*60:
   errors.append('本次更新達時間預算；剩餘日期由後續排程補抓');break
  try:
   raw_margin=None;raw_quotes=None
   try:raw_margin=fetch('marginTrading/MI_MARGN',d,selectType='ALL')
   except Exception as e:errors.append(d+' 資券明細：'+str(e))
   try:raw_quotes=fetch('afterTrading/MI_INDEX',d,type='ALLBUT0999')
   except Exception as e:errors.append(d+' 個股行情：'+str(e))
   if companies:
    rec=ranks.setdefault(d,{});rec['classification_date']=classification_date;re=[];qr={}
    if raw_quotes is not None:
     try:qr=rankings.quotes(raw_quotes);rec['sectors']=rankings.sector_rank(qr,companies)
     except Exception as e:re.append('產業：'+str(e))
    else:re.append('產業：個股行情未取得')
    if raw_margin is not None:
     try:rec['credit']=rankings.credit_rank(raw_margin,qr,companies)
     except Exception as e:re.append('資券：'+str(e))
    else:re.append('資券：明細未取得')
    rec['errors']=re
    if re:errors.extend(d+' 排行榜：'+x for x in re)
    print(d,'rankings', 'sectors' in rec,'credit' in rec,flush=True)
   if d in concept_dates:
    rec=ranks.setdefault(d,{});con=rec.setdefault('concepts',{});ce=[]
    if companies and raw_quotes is not None:
     try:con['listed']=concepts.summarize(rankings.quotes(raw_quotes),companies,'上市')
     except Exception as e:ce.append('上市族群：'+str(e))
    if otc:
     oq={}
     try:
      oq=concepts.otc_quotes(concepts.otc_fetch('afterTrading/dailyQuotes',d),otc)
      con['otc']=concepts.summarize(oq,otc,'上櫃')
     except Exception as e:ce.append('上櫃行情：'+str(e))
     try:rec['credit_otc']=concepts.otc_credit(concepts.otc_fetch('margin/balance',d),oq,otc)
     except Exception as e:ce.append('上櫃資券：'+str(e))
    else:ce.append('上櫃名單未取得')
    rec['concept_errors']=ce;rec['concept_attempt']=t.isoformat();errors.extend(d+' '+x for x in ce)
    print(d,'concepts',list(con), 'OTC credit','credit_otc' in rec,flush=True)
   if raw_margin is None:raise ValueError('融資資料未取得')
   shares,amount=margin_input(raw_margin)
   daily[d]['balance']=round(amount/100000,4)
   if raw_quotes is None:raise ValueError('個股行情未取得')
   quotes=quote_map(d,raw_quotes);cache[d]=quotes
   # First check recent official market closes, then individual monthly history.
   merged=dict(quotes); prior={}; notes=[]
   if set(shares)-set(merged):
    for old in [x for x in dates if x<d][:5]:
     if old not in cache:
      try:cache[old]=quote_map(old)
      except Exception:continue
     for k in set(shares)-set(merged):
      if k in cache[old]:merged[k]=cache[old][k];prior[k]=old
     if not set(shares)-set(merged):break
   for k in sorted(set(shares)-set(merged)):
    try:
     hit=resolve_price(k,d,stock_cache)
     if hit:
      pricedate,price=hit;merged[k]=price
      if pricedate<d:prior[k]=pricedate
     else:notes.append(k+' 查無最近一年歷史收盤價')
    except Exception as e:notes.append(k+' 個股補查失敗：'+str(e))
   unresolved=set(shares)-set(merged)
   if unresolved:
    count=sum(shares[k] for k in unresolved);coverage=(1-count/sum(shares.values()))*100
    raise ValueError('缺少收盤價；不估算；代號：'+', '.join(sorted(unresolved))+f'；張數覆蓋率 {coverage:.4f}%'+('；'+'；'.join(notes) if notes else ''))
   source='TWSE 估算'+(f'（含 {len(prior)} 檔前收）' if prior else '')
   daily[d].update(margin_pct=estimate(shares,amount,merged),source=source)
   if prior:print(d,'prior closes',', '.join(f'{k}={v}' for k,v in sorted(prior.items())),flush=True)
   print(d,'margin',daily[d]['margin_pct'],flush=True)
  except Exception as e:errors.append(d+': '+str(e));print(errors[-1],flush=True)
  # Persist partial progress even if later dates fail.
  if (i+1)%8==0:
   state.update(daily=[daily[k] for k in sorted(daily)],complete_months=sorted(complete),status={'message':'歷史補齊中','last_attempt':t.isoformat(),'errors':errors});write(state)
 state.update(daily=[daily[k] for k in sorted(daily)],complete_months=sorted(complete),status={'message':'部分更新／請查看紀錄' if errors else '資料更新完成','last_attempt':t.isoformat(),'errors':errors,'missing_margin':sum(r.get('margin_pct') is None for r in daily.values())});write(state)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--full',action='store_true');args=p.parse_args();run(args.full)
