# -*- coding: utf-8 -*-
"""Truthful receipts, versioned summary manifests and bounded record audits."""
import json,re
from base import canon,digest,now
from binding import Denied
class Completion:
 def init_completion(self):
  ddl="CREATE TABLE summary_manifest(summary_revision_id TEXT NOT NULL REFERENCES revision(revision_id),member_item_id TEXT NOT NULL REFERENCES item(item_id),member_revision_id TEXT NOT NULL REFERENCES revision(revision_id),PRIMARY KEY(summary_revision_id,member_item_id));CREATE INDEX summary_manifest_lookup ON summary_manifest(summary_revision_id);immutable_v1"
  checksum=digest(ddl);row=self.db.execute('SELECT checksum FROM migration WHERE version=3').fetchone()
  if row:
   if row[0]!=checksum:raise ValueError('summary migration checksum mismatch')
   return
  self.db.execute('begin immediate')
  try:
   row=self.db.execute('SELECT checksum FROM migration WHERE version=3').fetchone()
   if not row:
    self.db.execute('CREATE TABLE summary_manifest(summary_revision_id TEXT NOT NULL REFERENCES revision(revision_id),member_item_id TEXT NOT NULL REFERENCES item(item_id),member_revision_id TEXT NOT NULL REFERENCES revision(revision_id),PRIMARY KEY(summary_revision_id,member_item_id))')
    self.db.execute('CREATE INDEX summary_manifest_lookup ON summary_manifest(summary_revision_id)')
    for action in ('update','delete'):self.db.execute("CREATE TRIGGER immutable_summary_manifest_"+action+" BEFORE "+action+" ON summary_manifest BEGIN SELECT RAISE(ABORT,'immutable summary manifest'); END")
    self.db.execute('INSERT INTO migration VALUES(3,?,?)',(checksum,now()))
   elif row[0]!=checksum:raise ValueError('summary migration checksum mismatch')
   self.db.execute('commit')
  except BaseException:self.db.execute('rollback');raise
 def insert_revision(self,proposal,evidence,**kwargs):
  proposal=dict(proposal);manifest=proposal.get('payload',{}).get('nexus_summary')
  if manifest:
   payload=dict(proposal['payload']);manifest=dict(manifest);manifest['summary_version']=self.head(kwargs['item_id'])['version']+1 if kwargs.get('item_id') else 1;payload['nexus_summary']=manifest;proposal['payload']=payload
  result=super().insert_revision(proposal,evidence,**kwargs)
  if manifest:
   rows=self.db.execute("SELECT item_id,revision_id FROM current_item r WHERE "+self.visibility_sql(health=self.group(manifest['group_id'])[1]['domain']=='health' and getattr(self,'_health_access',False))+" AND EXISTS(SELECT 1 FROM relation e WHERE e.revision_id=r.revision_id AND e.predicate='for_group' AND e.object_item_id=?) ORDER BY item_id",(manifest['group_id'],)).fetchall()
   if digest(canon([tuple(r) for r in rows]))!=manifest['member_stamp']:raise ValueError('summary basis changed')
   self.db.executemany('INSERT INTO summary_manifest VALUES(?,?,?)',[(result['revision_id'],r['item_id'],r['revision_id']) for r in rows])
  return result
 def verify(self):
  result=super().verify()
  for r in self.db.execute("SELECT revision_id,payload_json FROM revision WHERE json_type(payload_json,'$.nexus_summary')='object'"):
   manifest=json.loads(r['payload_json'])['nexus_summary'];rows=self.db.execute('SELECT member_item_id,member_revision_id FROM summary_manifest WHERE summary_revision_id=? ORDER BY member_item_id',(r['revision_id'],)).fetchall()
   if len(rows)!=manifest['member_count'] or digest(canon([tuple(x) for x in rows]))!=manifest['member_stamp']:result['errors'].append('summary_manifest_mismatch')
  return result
 def receipt(self,result):
  if not result.get('committed'):return result
  receipts=[]
  entries=result.get('results') or ([result] if result.get('item_id') else [])
  for entry in entries:
   rid=entry.get('revision_id')
   if rid:
    row=self.db.execute('SELECT r.*,i.kind FROM revision r JOIN item i USING(item_id) WHERE r.revision_id=?',(rid,)).fetchone()
    if not row:continue
    h=dict(row)
   else:h=self.head(entry['item_id'])
   payload=json.loads(h['payload_json']);mode='verbatim' if json.loads(h['extraction_json']).get('method')=='L0_verbatim_no_llm' else 'structured'
   grouping=payload.get('grouping',{});gid=grouping.get('group_id');gname=None
   if gid:
    try:gname=self.group(gid)[1]['name']
    except (Denied,ValueError):gname='原档案（当前不可查询）'
   finance=self.db.execute('SELECT * FROM financial_detail WHERE revision_id=?',(h['revision_id'],)).fetchone()
   task=self.db.execute('SELECT * FROM task_detail WHERE revision_id=?',(h['revision_id'],)).fetchone()
   schedule=self.db.execute('SELECT * FROM schedule_detail WHERE revision_id=?',(h['revision_id'],)).fetchone()
   categories={'life':'生活','生活':'生活','旅行':'生活','travel':'生活','work':'工作','工作':'工作','uncategorized':'未分类','unclassified':'未分类','unknown':'未分类','health':'健康','健康':'健康'};domain=categories.get(h['domain'],h['domain'])
   parts=['已保存原话（明细尚未整理）' if mode=='verbatim' else '已保存']
   parts.append('内容：'+h['title'][:80])
   if payload.get('nexus_summary'):
    try:summary_name=self.group(payload['nexus_summary']['group_id'])[1]['name']
    except (Denied,ValueError):summary_name='原档案（当前不可查询）'
    parts.append('汇总快照：'+summary_name)
   elif gname:parts.append('档案：'+gname)
   elif payload.get('nexus_group'):parts.append('档案卡：'+payload['nexus_group']['name'])
   elif grouping.get('state')=='pending':parts.append('归属待确认，暂不计入档案合计')
   else:parts.append('未关联档案')
   parts.append('分类：'+domain)
   if finance:
    amount=finance['amount_minor'];scale=finance['scale'];units=10**scale;value=str(amount//units)+(('.'+str(amount%units).zfill(scale)) if scale else '')
    direction={'expense':'支出','income':'收入','refund':'退款'}[finance['direction']];cls={'booked':'已入账','quote':'报价','budget':'预算','commitment':'承诺/待支付性质'}[finance['entry_class']]
    parts.append(cls+direction+' '+value+' '+finance['currency'])
   if task:parts.append('待办：'+{'open':'未完成','done':'已完成','cancelled':'已取消','paused':'暂停'}[task['state']])
   if schedule:parts.append('日程：'+schedule['time_expression'])
   if h['status']=='deleted':parts=['日程已取消；已退出未来日程查询，原话和历史版本保留' if schedule and payload.get('schedule_state')=='cancelled' else '结构化记录已移出有效查询；原话和历史版本保留']
   if payload.get('nexus_summary'):
    parts.append('截至'+payload['nexus_summary']['generated_at'])
    status=self.summary_status(h)
    parts.append(status['message'])
   receipts.append({'item_id':h['item_id'],'revision_id':h['revision_id'],'stored':True,'status':h['status'],'schedule_state':payload.get('schedule_state','planned' if schedule else None),'task_detail_saved':bool(task),'structure_mode':mode,'domain':{'生活':'life','旅行':'life','travel':'life','工作':'work','健康':'health','unknown':'unclassified','uncategorized':'unclassified'}.get(h['domain'],h['domain']),'legacy_domain':h['domain'],'group_id':gid,'group_name':gname,'grouping_state':grouping.get('state','ungrouped'),'financial_detail_saved':bool(finance),'user_text':'；'.join(parts),'as_of_revision':h['revision_id']})
  return {**result,'receipts':receipts,'user_confirmation':'\n'.join(r['user_text'] for r in receipts)}
 def member_manifest(self,gid):
  rows=self.db.execute("SELECT item_id,revision_id FROM current_item r WHERE "+self.visibility_sql(health=self.group(gid)[1]['domain']=='health' and getattr(self,'_health_access',False))+" AND EXISTS(SELECT 1 FROM relation e WHERE e.revision_id=r.revision_id AND e.predicate='for_group' AND e.object_item_id=?) ORDER BY item_id",(gid,)).fetchall()
  return {'member_stamp':digest(canon([tuple(r) for r in rows])),'member_count':len(rows)}
 def prepare_summary(self,p,b):
  gid=p.get('summary_for_group')
  if not gid:return p
  if p.get('kind','record')!='record' or any(k in p for k in ('financial','task','schedule','group_profile','context_action','group_id')):raise ValueError('summary must be a separate record without financial details or membership')
  h,g=self.group(gid);raw=b['text'];matches=[x for x in self.catalog() if any(a in raw for a in [x['name']]+x.get('aliases',[]))]
  if not any(a in raw for a in [gid,g['name']]+g.get('aliases',[])) or (len(matches)>1 and not self.distinguished(gid,g,raw,matches)):raise ValueError('summary requires explicit unambiguous group')
  if not re.search('汇总|总结|小结',raw):raise ValueError('summary generation needs explicit request')
  summary=self._group_query({'template':'group_summary','group_id':gid},b)
  p=dict(p);payload=dict(p.get('payload',{}));payload['nexus_summary']={'group_id':gid,**self.member_manifest(gid),'generated_at':summary['as_of'],'as_of':summary['as_of'],'scope':'all_current_active_private_group_members','record_count':summary['records_total'],'financial_revision_count':summary['financial_records'],'totals':summary['totals'],'basis':'current_active_private_members'}
  payload.pop('grouping',None)
  p['payload']=payload;p['domain']=g['domain'];p['relations']=[{'object_item_id':gid,'predicate':'summary_of','qualifiers':{}}]
  p['title']=p.get('title') or g['name']+'｜汇总快照'
  lines=[g['name']+'汇总快照；截至'+payload['nexus_summary']['generated_at'],f"有效记录{summary['records_total']}条，财务明细{summary['financial_records']}条。"]
  for t in summary['totals']:
   scale=t['scale'];amount=t['total_minor'];unit=10**scale;money=str(amount//unit)+(('.'+str(amount%unit).zfill(scale)) if scale else '')
   lines.append(f"{t['currency']} {t['direction']} {t['entry_class']}：{money}（{t['count']}笔）")
  lines.append('报价/预算/承诺分列；未归组及未结构化费用不计入。当前合计以实时明细为准。')
  p['body']='\n'.join(lines);return p
 def summary_status(self,h):
  payload=json.loads(h['payload_json']);manifest=payload.get('nexus_summary')
  if manifest:
   gid=manifest['group_id']
   try:self.group(gid);current=self.member_manifest(gid)
   except (Denied,ValueError):return {'state':'unavailable','needs_update':True,'reason':'档案当前不可查询','message':'档案当前不可查询，请核对后再使用汇总。'}
   stale=manifest['member_stamp']!=current['member_stamp']
   return {'state':'stale' if stale else 'current','needs_update':stale,'group_id':gid,'generated_at':manifest['generated_at'],'snapshot_member_count':manifest['member_count'],'current_member_count':current['member_count'],'message':'明细已有变化，这份文字快照需要更新；金额请用实时统计。' if stale else '这份快照与当前已关联明细一致。'}
  if payload.get('nexus_group') and ('汇总' in h['title'] or 'financial_item_ids' in payload):return {'state':'legacy_untracked','needs_update':True,'group_id':h['item_id'],'message':'历史文字汇总没有完整版本清单，不能视为当前合计；请查询实时统计或生成新快照。'}
  return None
 def decorate_hits(self,result):
  if isinstance(result,dict) and 'hits' in result:
   for hit in result['hits']:
    if hit.get('item_id'):
     status=self.summary_status(self.head(hit['item_id']))
     if status:hit['summary_status']=status
  return result
 def completion_query(self,args,b):
  self.db.execute('begin')
  try:
   result=self._completion_query(args,b);self.db.execute('commit');return result
  except BaseException:self.db.execute('rollback');raise
 def _completion_query(self,args,b):
  if args.get('start') or args.get('end') or args.get('entity_id'):raise ValueError('unsupported audit date filters')
  gid=args.get('group_id');h,g=self.group(gid);template=args['template']
  if template=='group_snapshots':
   rows=self.db.execute("SELECT r.* FROM current_item r WHERE "+self.visibility_sql(health=g['domain']=='health' and getattr(self,'_health_access',False))+" AND (json_extract(r.payload_json,'$.nexus_summary.group_id')=? OR r.item_id=?) ORDER BY r.created_at DESC,r.item_id",(gid,gid)).fetchall()
   values=[]
   for r in rows:
    status=self.summary_status(dict(r))
    if status:values.append({'item_id':r['item_id'],'revision_id':r['revision_id'],'title':r['title'],'summary_status':status})
   return self.page_values(values,args,'snapshots:'+gid)
  if template=='group_snapshot_members':
   sh=self.head(args.get('snapshot_item_id'));manifest=json.loads(sh['payload_json']).get('nexus_summary')
   if (sh['visibility']!='private' and not (sh['domain']=='health' and getattr(self,'_health_access',False))) or sh['status']!='active' or not manifest or manifest['group_id']!=gid:raise Denied('snapshot_not_available')
   sql="SELECT m.member_item_id AS item_id,m.member_revision_id AS revision_id,old.title, CASE WHEN f.revision_id IS NULL THEN 0 ELSE 1 END AS has_financial_detail FROM summary_manifest m LEFT JOIN financial_detail f ON f.revision_id=m.member_revision_id JOIN revision old ON old.revision_id=m.member_revision_id JOIN item i ON i.item_id=m.member_item_id JOIN revision current ON current.revision_id=i.head_revision_id WHERE m.summary_revision_id=? AND "+self.visibility_sql('old',health=g['domain']=='health' and getattr(self,'_health_access',False))+" AND "+self.visibility_sql('current',health=g['domain']=='health' and getattr(self,'_health_access',False))+" AND current.status='active' ORDER BY m.member_item_id"
   result=self.page_sql(sql,[sh['revision_id']],args,'snapshot-members:'+sh['revision_id']);result['snapshot_created_at']=manifest['generated_at'];result['snapshot_member_count']=manifest['member_count'];result['snapshot_as_of']=manifest.get('as_of',manifest['generated_at']);result['summary_version']=manifest.get('summary_version',sh['version']);result['financial_revision_set']='member_revision_id with has_financial_detail=1, including all pages';return result
  if template!='group_audit':raise ValueError('invalid completion query')
  members={r[0] for r in self.db.execute("SELECT item_id FROM current_item r WHERE r.visibility='private' AND r.domain NOT IN ('health','健康') AND EXISTS(SELECT 1 FROM relation e WHERE e.revision_id=r.revision_id AND e.predicate='for_group' AND e.object_item_id=?)",(gid,))}
  rows=self.db.execute("SELECT r.* FROM current_item r WHERE visibility='private' AND domain NOT IN ('health','健康') ORDER BY item_id").fetchall();values=[];seen={};aliases=[g['name']]+g.get('aliases',[])
  for row in rows:
   r=dict(row);iid=r['item_id'];payload=json.loads(r['payload_json']);tags=json.loads(r['tags_json'])
   if iid==gid or payload.get('nexus_summary'):continue
   explicit=any(a in tags for a in aliases) or ('trip:'+gid) in tags or payload.get('trip_item_id')==gid
   textual=any(a in r['title']+'\n'+r['body'] for a in aliases)
   pending=payload.get('grouping',{}).get('state')=='pending' and (gid in payload.get('grouping',{}).get('candidate_group_ids',[]) or textual)
   categories=[]
   if iid not in members and explicit:categories.append(('missing_explicit_membership','已有明确标签/档案编号但缺正式关联；可受控补齐'))
   elif iid not in members and textual:categories.append(('possible_membership','文字提及档案，需核对；未自动归组'))
   if pending:categories.append(('pending_membership','归属待确认'))
   if iid in members:
    finance=self.db.execute('SELECT 1 FROM financial_detail WHERE revision_id=?',(r['revision_id'],)).fetchone()
    if not finance and re.search('元|付款|支付|消费|费用|加油|门票',r['title']+' '+r['body']):categories.append(('possible_unstructured_cost','可能含费用或汇总；需核对是否已有独立明细，未自动新增交易'))
    key=digest(re.sub(r'\s+','',r['title']+'\n'+r['body']))
    if key in seen:categories.append(('possible_duplicate','内容与另一独立记录相同；保留两条，未自动合并'))
    else:seen[key]=iid
   for category,message in categories:values.append({'category':category,'item_id':iid,'revision_id':r['revision_id'],'title':r['title'],'message':message})
  counts={}
  for v in values:counts[v['category']]=counts.get(v['category'],0)+1
  result=self.page_values(values,args,'audit:'+gid);result.update({'finding_counts':counts,'linked_records':len(members),'scope':'all_current_active_private_nexus_records','no_automatic_expense_or_merge':True})
  return result
