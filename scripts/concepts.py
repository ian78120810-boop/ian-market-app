"""Curated representative concept baskets; TPEx historical reports. No paid APIs."""
import json,re,time,urllib.request,urllib.parse
from pathlib import Path
from datetime import date
from rankings import numeric, fields, tables, INDUSTRIES
GROUPS={k:set(v.split()) for k,v in json.loads(Path(__file__).with_name('concepts.json').read_text(encoding='utf-8')).items()}
KEYS={'margin_up':('margin_delta',1),'margin_down':('margin_delta',-1),'short_up':('short_delta',1),'short_down':('short_delta',-1),'margin_balance':('margin_balance',1),'short_balance':('short_balance',1)}
def http(url):
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 TaiwanMarketDashboard','Accept':'application/json'})
  with urllib.request.urlopen(req,timeout=25) as f:return json.load(f)
 finally:time.sleep(3)
def otc_companies():
 rows=http('https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O')
 out={str(r['公司代號']).strip():INDUSTRIES.get(str(r['產業別']).strip().zfill(2),'其他') for r in rows if r.get('公司代號') and r.get('產業別')}
 if len(out)<500:raise ValueError('上櫃公司名單不足')
 return out
def matches_day(obj,day):
 d=date.fromisoformat(day); roc=d.year-1911
 candidates={day,day.replace('-','/'),day.replace('-',''),f'{roc}/{d.month:02d}/{d.day:02d}',f'{roc}{d.month:02d}{d.day:02d}',f'{roc}年{d.month:02d}月{d.day:02d}日',f'{roc}年{d.month}月{d.day}日'}
 metadata=' '.join(str(t.get(k,'')) for t in tables(obj) for k in ('date','reportDate','title','subtitle','queryDate'))
 return any(x in metadata for x in candidates)
def otc_fetch(path,day):
 obj=http('https://www.tpex.org.tw/www/zh-tw/'+path+'?'+urllib.parse.urlencode({'date':day.replace('-','/'),'response':'json','id':''}))
 if not isinstance(obj,dict) or not matches_day(obj,day):raise ValueError('上櫃來源日期未能驗證 '+day)
 return obj
def field(f,*names):
 for n in names:
  for i,x in enumerate(f):
   if x==n:return i
 for n in names:
  for i,x in enumerate(f):
   if n in x:return i
 raise ValueError('缺欄位 '+str(names))
def otc_quotes(obj,companies):
 for t in tables(obj):
  f=fields(t)
  try:ci,ni,pi,di,mi=[field(f,*names) for names in [('代號',),('名稱',),('收盤','收盤價'),('漲跌',),('成交金額(元)','成交金額')]]
  except ValueError:continue
  if '仟元' in f[mi] or '千元' in f[mi]:scale=1000
  else:scale=1
  out={}
  for r in t.get('data',[]):
   code=str(r[ci]).strip()
   if code not in companies:continue
   p=numeric(r[pi]);delta=numeric(r[di]);v=numeric(r[mi]);change=None
   if p is not None and delta is not None and p>0 and p-delta>0:change=100*delta/(p-delta)
   if v is not None and v>=0:out[code]={'code':code,'name':str(r[ni]).strip(),'close':p,'money':v*scale,'change':change}
  if len(out)>=300:return out
 raise ValueError('上櫃個股成交明細不足或欄位不同')
def otc_credit(obj,q,companies):
 for t in tables(obj):
  f=fields(t)
  try:
   ci,ni=field(f,'代號'),field(f,'名稱')
   try:mp,mt,sp,st=[field(f,*a) for a in [('資前餘額','融資前日餘額','資前日餘額'),('資今餘額','融資今日餘額','資今日餘額','資餘額'),('券前餘額','融券前日餘額','券前日餘額'),('券今餘額','融券今日餘額','券今日餘額','券餘額')]]
   except ValueError:
    prev=[i for i,x in enumerate(f) if '前日餘額' in x];today=[i for i,x in enumerate(f) if '今日餘額' in x]
    if len(prev)!=2 or len(today)!=2 or not prev[0]<today[0]<prev[1]<today[1]:continue
    mp,mt,sp,st=prev[0],today[0],prev[1],today[1]
   if len({mp,mt,sp,st})!=4:continue
  except ValueError:continue
  out=[]
  for r in t.get('data',[]):
   code=str(r[ci]).strip()
   if code not in companies:continue
   a,b,c,d=[numeric(r[i]) for i in (mp,mt,sp,st)]
   if any(x is None or x<0 or not x.is_integer() for x in (a,b,c,d)):raise ValueError('上櫃資券欄位缺漏 '+code)
   x=q.get(code,{})
   out.append(dict(code=code,name=str(r[ni]).strip(),sector=companies[code],close=x.get('close'),change=x.get('change'),margin_delta=int(b-a),short_delta=int(d-c),margin_balance=int(b),short_balance=int(d),market='上櫃'))
  if len(out)>=300:return rank(out)
 raise ValueError('上櫃資券明細不足或欄位不同')
def rank(rows):
 return {k:sorted([r for r in rows if r[m]*sign>0],key=lambda r:(-r[m]*sign,r['code']))[:10] for k,(m,sign) in KEYS.items()}
def summarize(q,companies,market):
 out={}
 for name,codes in GROUPS.items():
  stocks=[]
  for k in sorted(codes & q.keys() & companies.keys()):
   r=q[k];stocks.append(dict(code=k,name=r['name'],market=market,amount=round(r['money']/1e8,5),change=r['change'],close=r['close']))
  if stocks:out[name]=stocks
 return out
