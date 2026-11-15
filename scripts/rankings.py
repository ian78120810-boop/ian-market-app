"""TWSE listed-company turnover and credit rankings; no external dependencies."""
import json, re, urllib.request, collections, math
INDUSTRIES=dict(zip('01 02 03 04 05 06 08 09 10 11 12 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 80'.split(), '水泥 食品 塑膠 紡織 電機機械 電器電纜 玻璃陶瓷 造紙 鋼鐵 橡膠 汽車 建材營造 航運 觀光餐旅 金融保險 貿易百貨 綜合 其他 化學 生技醫療 油電燃氣 半導體 電腦及週邊 光電 通信網路 電子零組件 電子通路 資訊服務 其他電子 文化創意 農業科技 電子商務 綠能環保 數位雲端 運動休閒 居家生活 管理股票'.split()))
URL='https://openapi.twse.com.tw/v1/opendata/t187ap03_L'
def numeric(x):
 try:
  v=float(str(x).replace(',','').replace('%','').strip());return v if math.isfinite(v) else None
 except (TypeError,ValueError):return None

def fields(t):return [re.sub(r'\s+','',str(x)) for x in t.get('fields',[])]
def pick(fs,k):return next(i for i,f in enumerate(fs) if k in f)
def tables(obj):return [obj]+obj.get('tables',[])
def company_map():
 req=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0 TaiwanMarketDashboard','Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=35) as f: rows=json.load(f)
 if not isinstance(rows,list):raise ValueError('上市公司分類格式錯誤')
 out={str(r['公司代號']).strip():INDUSTRIES.get(str(r['產業別']).strip().zfill(2),'產業 '+str(r['產業別']).strip()) for r in rows if r.get('公司代號') and r.get('產業別')}
 if len(out)<500:raise ValueError('上市公司分類筆數不足')
 return out, str(rows[0].get('出表日期',''))

def quotes(obj):
 for t in tables(obj):
  f=fields(t)
  if not all(any(k in x for x in f) for k in ('證券代號','證券名稱','成交金額','收盤價','漲跌價差','漲跌(+/-)')) or not t.get('data'):continue
  ci,ni,ti,pi,di,si=[pick(f,k) for k in ('證券代號','證券名稱','成交金額','收盤價','漲跌價差','漲跌(+/-)')]
  out={}
  for r in t['data']:
   code=str(r[ci]).strip();money=numeric(r[ti]);close=numeric(r[pi]);delta=numeric(r[di]);sign=re.sub('<[^>]*>','',str(r[si])).strip()
   change=None
   if close is not None and close>0 and delta is not None and sign in ('+','-','＋','－',''):
    delta=abs(delta)*(-1 if sign in ('-','－') else 1)
    if (sign or delta==0) and close-delta>0:change=round(delta/(close-delta)*100,2)
   if money is not None and money>=0:out[code]={'code':code,'name':str(r[ni]).strip(),'money':money,'close':close if close and close>0 else None,'change':change}
  if out:return out
 raise ValueError('找不到個股成交金額明細')

def sector_rank(q,companies):
 groups=collections.defaultdict(list)
 for code,r in q.items():
  if code in companies:groups[companies[code]].append(r)
 total=sum(r['money'] for rs in groups.values() for r in rs)
 if not total or sum(map(len,groups.values()))<100:raise ValueError('產業成交資料不足')
 result=[]
 for name,rs in groups.items():
  money=sum(r['money'] for r in rs);changes=[r['change'] for r in rs if r['change'] is not None]
  result.append({'name':name,'amount':round(money/1e8,3),'share':round(money/total*100,2),'up':sum(x>0 for x in changes),'down':sum(x<0 for x in changes),'count':len(rs),'leaders':[{'code':r['code'],'name':r['name'],'amount':round(r['money']/1e8,3)} for r in sorted(rs,key=lambda x:(-x['money'],x['code']))[:3]]})
 return sorted(result,key=lambda x:(-x['amount'],x['name']))[:10]

def credit_rank(obj,q,companies):
 for t in tables(obj):
  f=fields(t);today=[i for i,x in enumerate(f) if '今日餘額' in x];prev=[i for i,x in enumerate(f) if '前日餘額' in x]
  if len(today)!=2 or len(prev)!=2 or not any('代號' in x for x in f) or not any('名稱' in x for x in f) or not t.get('data'):continue
  # The first set of balances is financing, the second short selling, per TWSE report.
  if not prev[0]<today[0]<prev[1]<today[1]:raise ValueError('資券餘額欄位順序不符')
  ci,ni=pick(f,'代號'),pick(f,'名稱');rows=[];sums=[0,0]
  for r in t['data']:
   code=str(r[ci]).strip();values=[numeric(r[i]) for i in (prev[0],today[0],prev[1],today[1])]
   if any(v is None or v<0 or not v.is_integer() for v in values):raise ValueError('資券數值缺漏：'+code)
   mp,mt,sp,st=map(int,values);sums[0]+=mt;sums[1]+=st
   if code not in companies:continue
   x=q.get(code,{})
   rows.append({'code':code,'name':str(r[ni]).strip(),'sector':companies[code],'close':x.get('close'),'change':x.get('change'),'margin_delta':mt-mp,'short_delta':st-sp,'margin_balance':mt,'short_balance':st})
  # Check raw full report totals (all securities) before the listed-company filter.
  totals=[]
  for name in ('融資','融券'):
   val=None
   for tt in tables(obj):
    ff=fields(tt)
    if not any('項目' in x for x in ff) or not any('今日餘額' in x for x in ff):continue
    for r in tt.get('data',[]):
     label=str(r[pick(ff,'項目')])
     if name in label and '交易單位' in label:val=numeric(r[pick(ff,'今日餘額')]);break
   totals.append(val)
  if not rows or any(v is None or abs(s-v)>max(1,v*.001) for s,v in zip(sums,totals)):raise ValueError('明細與資券交易單位總數不符')
  out={}
  for key,metric,direction in [('margin_up','margin_delta',1),('margin_down','margin_delta',-1),('short_up','short_delta',1),('short_down','short_delta',-1),('margin_balance','margin_balance',1),('short_balance','short_balance',1)]:
   out[key]=sorted((r for r in rows if r[metric]*direction>0),key=lambda r:(-r[metric]*direction,r['code']))[:10]
  return out
 raise ValueError('找不到資券個股明細（兩組前日／今日餘額）')
