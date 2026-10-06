"""Source-bound dossiers, conservative membership and snapshot pagination."""
import base64,datetime as dt,json,re
from pathlib import Path
from base import canon,digest,now,Conflict
from binding import Denied

DDL="""CREATE TABLE group_context (
 context_id TEXT PRIMARY KEY, scope TEXT NOT NULL, group_id TEXT REFERENCES item(item_id),
 source_id TEXT NOT NULL REFERENCES source(source_id), event_at REAL NOT NULL,
 expires_at REAL NOT NULL, created_at TEXT NOT NULL);
 CREATE INDEX group_context_scope ON group_context(scope,event_at);
 CREATE TRIGGER immutable_group_context_update BEFORE UPDATE ON group_context BEGIN SELECT RAISE(ABORT,'immutable context'); END;
 CREATE TRIGGER immutable_group_context_delete BEFORE DELETE ON group_context BEGIN SELECT RAISE(ABORT,'immutable context'); END;
"""
class Groups:
 def init_groups(self):
  checksum=digest(DDL)
  existing=self.db.execute('select checksum from migration where version=2').fetchone()
  if existing:
   if existing[0]!=checksum:raise ValueError('group migration checksum mismatch')
   return
  self.db.execute('begin immediate')
  try:
   row=self.db.execute('select checksum from migration where version=2').fetchone()
   if row and row[0]!=checksum:raise ValueError('group migration checksum mismatch')
   if not row:
    self.db.execute('CREATE TABLE group_context(context_id TEXT PRIMARY KEY,scope TEXT NOT NULL,group_id TEXT REFERENCES item(item_id),source_id TEXT NOT NULL REFERENCES source(source_id),event_at REAL NOT NULL,expires_at REAL NOT NULL,created_at TEXT NOT NULL)')
    self.db.execute('CREATE INDEX group_context_scope ON group_context(scope,event_at)')
    for action in ('update','delete'):
     self.db.execute("CREATE TRIGGER immutable_group_context_"+action+" BEFORE "+action+" ON group_context BEGIN SELECT RAISE(ABORT,'immutable context'); END")
    self.db.execute('insert into migration values(2,?,?)',(checksum,now()))
   self.db.execute('commit')
  except BaseException:self.db.execute('rollback');raise
 def catalog(self):
  rows=self.db.execute("SELECT item_id,title,domain,payload_json FROM current_item WHERE visibility='private' AND json_type(payload_json,'$.nexus_group')='object' ORDER BY item_id").fetchall()
  if getattr(self,'_health_access',False):rows+=self.db.execute("SELECT item_id,title,domain,payload_json FROM current_item WHERE domain='health' AND visibility='restricted' AND json_type(payload_json,'$.nexus_group')='object' ORDER BY item_id").fetchall()
  else:rows=[r for r in rows if r['domain'] not in ('health','健康')]
  return [{'group_id':r['item_id'],'title':r['title'],**json.loads(r['payload_json'])['nexus_group']} for r in rows]
 def group(self,gid):
  h=self.head(gid);g=json.loads(h['payload_json']).get('nexus_group')
  if not g or (h['visibility']!='private' and not (h['domain']=='health' and getattr(self,'_health_access',False))) or (h['domain']=='health' and not getattr(self,'_health_access',False)) or h['status']!='active':raise Denied('group_unavailable')
  return h,g
 def profile(self,p,raw):
  g=p.get('group_profile')
  if g is None:return p
  if p.get('kind','record')!='record':raise ValueError('group profile belongs to primary record')
  if not isinstance(g,dict) or set(g)-{'name','aliases','state','start_date','end_date'}:raise ValueError('invalid group profile')
  name=g.get('name');aliases=g.get('aliases',[])
  if not isinstance(name,str) or not 1<=len(name)<=100 or not isinstance(aliases,list) or len(aliases)>10 or any(not isinstance(a,str) or not 2<=len(a)<=100 for a in aliases):raise ValueError('bounded group names required')
  if not any(x in raw for x in [name]+aliases):raise ValueError('group name must be present in source')
  state=g.get('state','open')
  if state not in ('open','closed'):raise ValueError('invalid group state')
  if state=='closed' and not re.search('结束|关闭|完成',raw):raise ValueError('closing group needs explicit instruction')
  for key in ('start_date','end_date'):
   if g.get(key):dt.date.fromisoformat(g[key])
  if g.get('end_date') and g.get('start_date') and g['end_date']<g['start_date']:raise ValueError('group date range')
  if p.get('domain') not in ('life','work','health'):raise ValueError('group needs life/work/health domain')
  p['payload']={**p.get('payload',{}),'nexus_group':{**g,'aliases':list(dict.fromkeys(aliases)),'state':state,'domain':p['domain']}}
  return p
 def distinguished(self,gid,g,raw,matches):
  if gid in raw:return True
  if g.get('start_date'):
   date=dt.date.fromisoformat(g['start_date'])
   forms=[g['start_date'],g['start_date'].replace('-',''),f'{date.year}年{date.month}月{date.day}日']
   if any(x in raw for x in forms):return True
  others=[x for x in matches if x['group_id']!=gid]
  return any(a in raw and all(a not in [x['name']]+x.get('aliases',[]) for x in others) for a in [g['name']]+g.get('aliases',[]))
 def event_time(self,b):
  ts=b['event'].get('timestamp') or b['event'].get('message',{}).get('timestamp')
  return ts/1000 if isinstance(ts,(int,float)) else dt.datetime.fromisoformat(ts.replace('Z','+00:00')).timestamp()
 def scope(self,b):return digest(canon([self.binder.settings['agent'],b['ctx']['channel'],b['ctx']['conversationRef']]))
 def context(self,b):
  t=self.event_time(b)
  row=self.db.execute('SELECT * FROM group_context WHERE scope=? AND event_at<=? ORDER BY event_at DESC,created_at DESC,context_id DESC LIMIT 1',(self.scope(b),t)).fetchone()
  if not row or not row['group_id'] or row['expires_at']<t:return None
  try:h,g=self.group(row['group_id'])
  except (Denied,ValueError):return None
  date=dt.datetime.fromtimestamp(t,dt.timezone(dt.timedelta(hours=8))).date().isoformat()
  if g['state']!='open' or (g.get('end_date') and date>g['end_date']):return None
  return row['group_id']
 def excluded_groups(self,raw,catalog):
  # Negation is checked against trusted original text, before model hints or context.
  excluded=set()
  for g in catalog:
   for alias in [g['group_id'],g['name']]+g.get('aliases',[]):
    if not alias:continue
    a=re.escape(alias)
    if re.search(r'(?:不属于|不归入|不归|不计入|不要归入|不要关联到|取消关联|移出)[「“\s]*'+a,raw) or re.search(a+r'[」”\s]*(?:无关|之外)',raw):
     excluded.add(g['group_id'])
  return excluded
 def prepare_group(self,p,b,*,old=None,fallback=False):
  p=dict(p);raw=b['text']
  if old and p.get('group_profile') is not None:
   prior=json.loads(old['payload_json']).get('nexus_group',{});incoming=dict(p['group_profile']);desired=incoming.get('state',prior.get('state','open'))
   if prior.get('state')=='closed' and desired=='open':
    if not re.search('重新打开|重新开启|重新开放|重开档案',raw) or re.search('不要重新|不重新|不要重开|不重开',raw):raise ValueError('reopening a closed group requires explicit instruction; context activation is not reopening')
   p['group_profile']={**{k:v for k,v in prior.items() if k in ('name','aliases','state','start_date','end_date')},**incoming}
  p=self.profile(p,raw);payload=dict(p.get('payload',{}))
  # Existing dossier metadata may only be changed via the validated group_profile field.
  if old:
   old_payload=json.loads(old['payload_json'])
   if 'nexus_group' in old_payload and 'group_profile' not in p:
    payload['nexus_group']=old_payload['nexus_group']
  p['payload']=payload
  if 'nexus_group' in payload or p.get('summary_for_group'):return p
  catalog=self.catalog();excluded=self.excluded_groups(raw,catalog);matches=[g for g in catalog if g['group_id'] not in excluded and any(a and a in raw for a in [g['name']]+g.get('aliases',[]))]
  gid=p.get('group_id');hint=p.get('group_name');existing=[r['object_item_id'] for r in p.get('relations',[]) if r['predicate']=='for_group']
  if gid=='':
   if not re.search('移出|不归|取消关联',raw) and not (set(existing)&excluded):raise ValueError('unlink requires explicit instruction')
   p['relations']=[r for r in p.get('relations',[]) if r['predicate']!='for_group'];p['payload'].pop('grouping',None);return p
  if gid in excluded:
   p['relations']=[r for r in p.get('relations',[]) if r['predicate']!='for_group' or r['object_item_id']!=gid]
   p['payload'].pop('grouping',None);return p
  if gid:
   h,g=self.group(gid);explicit=gid in raw or any(a in raw for a in [g['name']]+g.get('aliases',[]) if a)
   if explicit and len(matches)>1:
    # Dates or a literal stable ID distinguish same-name trips; never pick arbitrarily.
    distinguished=self.distinguished(gid,g,raw,matches)
    if not distinguished:raise Conflict('ambiguous_group_name_use_date_or_id')
   if not explicit:
    if self.context(b)!=gid or p.get('group_relevance')!='context' or p.get('domain')!=g['domain'] or fallback:raise ValueError('group requires explicit source or relevant active context')
    if g['domain']=='life' and re.search('单位|同事|会议|工作随手记',raw):raise ValueError('off_topic_group_context')
   reason='explicit' if explicit else 'context'
  elif hint and any(hint in [g['name']]+g.get('aliases',[]) for g in catalog if g['group_id'] in excluded):
   p['payload'].pop('grouping',None);return p
  elif hint:
   candidates=[g for g in matches if hint in [g['name']]+g.get('aliases',[])]
   if len(candidates)==1:gid=candidates[0]['group_id'];reason='explicit'
   else:reason='pending'
  elif old:
   # A correction retains its prior membership, including no membership.
   # Names mentioned in a separate query must not implicitly regroup this item.
   return p
  elif len(matches)==1:gid=matches[0]['group_id'];reason='explicit'
  elif len(matches)>1:reason='pending'
  else:
   active=self.context(b)
   if active in excluded:active=None
   relevant=active and p.get('domain','unclassified') in ('unclassified','uncategorized',self.group(active)[1]['domain'])
   reason='pending' if relevant else 'ungrouped'
  if gid:
   target=self.group(gid)[1]
   if p.get('domain')=='health' and target['domain']!='health':gid=None;reason='ungrouped'
  if gid:
   self.group(gid)
   p['relations']=[r for r in p.get('relations',[]) if r['predicate']!='for_group']+[{'object_item_id':gid,'predicate':'for_group','qualifiers':{'method':reason}}]
   p['payload']['grouping']={'state':'linked','group_id':gid,'method':reason}
  elif reason=='pending':
   candidates=[g['group_id'] for g in matches]
   active=self.context(b)
   if active in excluded:active=None
   if not candidates and active:candidates=[active]
   p['payload']['grouping']={'state':'pending','hint':hint or raw[:100],'candidate_group_ids':candidates}
  return p
 def change_context(self,p,item_id,b,sid):
  action=p.get('context_action')
  if not action:return
  if action not in ('activate','clear'):raise ValueError('invalid context action')
  h,g=self.group(item_id)
  named=item_id in b['text'] or any(a in b['text'] for a in [g['name']]+g.get('aliases',[]) if a)
  if action=='activate' and not named:raise ValueError('activation must name the group')
  if action=='activate':
   matches=[x for x in self.catalog() if any(a in b['text'] for a in [x['name']]+x.get('aliases',[]) if a)]
   if len(matches)>1 and not self.distinguished(item_id,g,b['text'],matches):raise Conflict('ambiguous_context_group')
  if action=='clear' and not named and self.context(b)!=item_id:raise ValueError('clear must name or refer to current group')
  if action=='activate':
   if not re.search('接下来|当前档案|开始记录|设为当前',b['text']) or g['state']!='open':raise ValueError('activation needs explicit instruction and open group')
  elif not re.search('结束|关闭|取消|停止|清除',b['text']):raise ValueError('clear needs explicit instruction')
  t=self.event_time(b);gid=item_id if action=='activate' else None
  self.db.execute('INSERT INTO group_context VALUES(?,?,?,?,?,?,?)',(digest(canon([sid,item_id,action])),self.scope(b),gid,sid,t,t+86400,now()))
 def group_query(self,args,b):
  self.db.execute('begin')
  try:result=self._group_query(args,b);self.db.execute('commit');return result
  except BaseException:self.db.execute('rollback');raise
 def _group_query(self,args,b):
  template=args['template'];catalog=self.catalog()
  if args.get('start') or args.get('end') or args.get('entity_id'):raise ValueError('group queries use fixed group membership; date filters not supported')
  if template=='group_context':return {'group_id':self.context(b),'scope':'current_owner_conversation','expires_within_hours':24}
  if template=='group_catalog':
   name=args.get('name');catalog=[g for g in catalog if not name or name in g['name'] or name in g.get('aliases',[])]
   return self.page_values(catalog,args,'catalog')
  gid=args.get('group_id');h,g=self.group(gid)
  if template=='group_records':
   where=self.visibility_sql(health=g['domain']=='health' and getattr(self,'_health_access',False))+" AND EXISTS(SELECT 1 FROM relation e WHERE e.revision_id=r.revision_id AND e.predicate='for_group' AND e.object_item_id=?)"
   sql='SELECT r.item_id,r.revision_id,r.title,r.domain,r.valid_from,r.time_expression,r.created_at,substr(r.body,1,160) AS excerpt FROM current_item r WHERE '+where+' ORDER BY coalesce(r.valid_from,r.created_at),r.item_id'
   return self.page_sql(sql,[gid],args,gid)
  if template=='group_pending':
   # Pending records are candidates, never included in totals; matching a hint is not membership.
   aliases=[g['name']]+g.get('aliases',[])
   values=[dict(r) for r in self.db.execute("SELECT item_id,revision_id,title,substr(body,1,160) AS excerpt,payload_json FROM current_item WHERE visibility='private' AND domain NOT IN ('health','健康') AND json_extract(payload_json,'$.grouping.state')='pending' ORDER BY item_id")]
   values=[{k:v for k,v in r.items() if k!='payload_json'} for r in values if gid in json.loads(r['payload_json']).get('grouping',{}).get('candidate_group_ids',[]) or any(a in json.loads(r['payload_json']).get('grouping',{}).get('hint','') for a in aliases)]
   return self.page_values(values,args,'pending:'+gid)
  if template=='group_summary':
   # Python integers avoid SQLite SUM overflow. All member rows are included, independent of page size.
   rows=self.db.execute("SELECT r.item_id,r.title,r.body,r.payload_json,f.* FROM current_item r LEFT JOIN financial_detail f USING(revision_id) WHERE "+self.visibility_sql(health=g['domain']=='health' and getattr(self,'_health_access',False))+" AND EXISTS(SELECT 1 FROM relation e WHERE e.revision_id=r.revision_id AND e.predicate='for_group' AND e.object_item_id=?)",(gid,)).fetchall()
   totals={};financial=0;unknown=0;candidates=0
   for r in rows:
    if r['amount_minor'] is not None:
     financial+=1;key=(r['currency'],r['scale'],r['direction'],r['entry_class']);bucket=totals.setdefault(key,[0,0]);bucket[0]+=r['amount_minor'];bucket[1]+=1
     if json.loads(r['payload_json']).get('payment_status')=='unknown':unknown+=1
    elif re.search('元|付款|支付|消费|费用|加油|门票',r['title']+' '+r['body']):candidates+=1
   pending=self._group_query({'template':'group_pending','group_id':gid,'limit':1},b)['total']
   return {'pending_candidates':pending,'group_id':gid,'name':g['name'],'records_total':len(rows),'financial_records':financial,'nonfinancial_records':len(rows)-financial,'payment_unknown_marked':unknown,'possible_financial_without_detail':candidates,'totals':[{'currency':k[0],'scale':k[1],'direction':k[2],'entry_class':k[3],'total_minor':v[0],'count':v[1]} for k,v in sorted(totals.items())],'coverage':'all_current_active_private_group_members','complete':True,'as_of':now(),'note':'报价/预算/承诺分列；非财务记录中的金额和待归组内容不计入。possible_financial_without_detail是关键词候选数，不能当作已确认漏账。'}
  raise ValueError('group query template not allowed')
 def stamp(self):return digest(canon([tuple(r) for r in self.db.execute('SELECT item_id,head_revision_id FROM item ORDER BY item_id')]))
 def cursor(self,args,key):
  limit=args.get('limit',10)
  if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=20:raise ValueError('page limit 1..20')
  stamp=self.stamp();identity=digest(canon([key,args.get('name')]))
  offset=0
  if args.get('cursor'):
   try:c=json.loads(base64.urlsafe_b64decode(args['cursor'].encode()))
   except Exception:raise ValueError('invalid cursor')
   if c.get('stamp')!=stamp or c.get('identity')!=identity:raise Conflict('records_changed_or_wrong_cursor_restart_query')
   offset=c.get('offset')
   if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:raise ValueError('invalid cursor offset')
  return limit,offset,stamp,identity
 def page_sql(self,sql,params,args,key):
  limit,offset,stamp,identity=self.cursor(args,key)
  count=self.db.execute('SELECT count(*) FROM ('+sql+')',params).fetchone()[0]
  rows=[dict(r) for r in self.db.execute(sql+' LIMIT ? OFFSET ?',params+[limit,offset])]
  return self.page_result(rows,count,offset,stamp,identity)
 def page_values(self,values,args,key):
  limit,offset,stamp,identity=self.cursor(args,key)
  return self.page_result(values[offset:offset+limit],len(values),offset,stamp,identity)
 def page_result(self,values,total,offset,stamp,identity):
  hits=[]
  for value in values:
   if len(canon(hits+[value]))>5500:break
   hits.append(value)
  end=offset+len(hits)
  if values and not hits:raise ValueError('single result exceeds page budget')
  cursor=base64.urlsafe_b64encode(canon({'offset':end,'stamp':stamp,'identity':identity}).encode()).decode() if end<total else None
  return {'hits':hits,'total':total,'returned':len(hits),'offset':offset,'next_cursor':cursor,'complete':cursor is None,'coverage':'current_active_private_records','snapshot':stamp}
