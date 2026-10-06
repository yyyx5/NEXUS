"""Nexus fixed operations. Context and source are supplied exclusively by host."""
import json,time,re,sqlite3
from pathlib import Path
from base import Nexus,Conflict,canon,digest,now
from binding import Binder,Denied,Pending
from groups import Groups
from completion import Completion
from queries import Queries
from taxonomy import Taxonomy,CANONICAL
PROPOSAL={'kind','domain','title','body','tags','payload','assertion_kind','certainty','perspective','temporal_status','valid_from','valid_to','time_expression','time_precision','timezone','visibility','status','reason','task','financial','schedule','aliases','quote','group_id','group_name','group_relevance','group_profile','context_action','summary_for_group'}
TOP={'nexus_save':{'proposals'},'nexus_update':{'item_id','expected_revision','reason','patch'},'nexus_search':{'text','domain','start','end','limit','tag','status','entity'},'nexus_query':{'template','start','end','entity_id','group_id','name','limit','cursor','snapshot_item_id','domain'},'nexus_get_source':{'item_id','source_id'},'nexus_delete_preview':{'item_id'}}
PREFIX=re.compile(r'(?:^|\n)\s*(?:记一下|帮我记录|生活随手记|工作随手记)[，,:：\s]')
class Core(Taxonomy,Queries,Completion,Groups,Nexus):
 def __init__(self,path,settings):
  super().__init__(path);self.binder=Binder(settings)
  self.db.execute('pragma journal_mode=wal');self.db.execute('pragma busy_timeout=800')
  checksum=digest((Path(__file__).parent.parent/'schema'/'schema.sql').read_text())
  row=self.db.execute('select checksum from migration where version=1').fetchone()
  if row and row[0]!=checksum:raise ValueError('migration checksum mismatch')
  self.db.execute('insert or ignore into migration values(1,?,?)',(checksum,now()))
  self.init_groups()
  self.init_completion()
 def validate(self,tool,args):
  if tool not in TOP or not isinstance(args,dict) or set(args)-TOP[tool] or len(canon(args))>64000:raise Denied('invalid_tool_arguments')
  def proposal(p):
   if not isinstance(p,dict) or set(p)-PROPOSAL:raise Denied('invalid_proposal_fields')
   if any(k in p.get('payload',{}) for k in ('nexus_group','grouping','nexus_summary','schedule_state')):raise Denied('reserved_group_payload')
   if 'domain' in p and p['domain'] not in CANONICAL:raise ValueError('AI may not create a top-level domain')
   if p.get('kind','record') not in ('record','entity','event','claim'):raise ValueError('kind not allowed')
   if len(canon(p.get('payload',{})))>4000 or len(p.get('tags',[]))>20 or len(p.get('aliases',[]))>20:raise ValueError('proposal budget')
   if any(k in canon(p.get('payload',{})) for k in ('archive_event_id','source_path','attachment_path','senderId','sessionKey')):raise Denied('identity fields not accepted')
  if tool=='nexus_save':
   ps=args.get('proposals');
   if not isinstance(ps,list) or not 1<=len(ps)<=10:raise ValueError('batch requires 1..10 proposals')
   for p in ps:proposal(p)
   if any(p.get('schedule') and p.get('status')=='deleted' for p in ps):raise ValueError('cancel original schedule with nexus_update; cannot save a deleted schedule')
   if ps[0].get('kind','record')!='record':raise ValueError('first proposal must be primary record')
  if tool=='nexus_update':
   if not args.get('item_id') or not args.get('expected_revision') or not isinstance(args.get('reason'),str) or not 1<=len(args['reason'])<=500:raise ValueError('update requires identity revision reason')
   proposal(args.get('patch'))
 def source(self,b,r):
  ctx=b['ctx'];sid=b['archive_event_id'];raw=b['text']
  if not raw or len(raw)>200000:raise ValueError('source text budget')
  locator={'type':'archive','archive_event_id':sid,'attachments':r.get('attachments',[])}
  row={'source_id':sid,'namespace':'archive','external_id':sid,'content_sha256':digest(raw),'raw_text':raw,'locator_json':canon(locator),'observed_at':now(),'schema_version':r.get('schema_version',1),'archive_event_id':sid,'logical_event_id':r.get('logical_event_id'),'source_event_id':b['event']['id'],'source_event_sha256':b['event_sha256'],'record_sha256':r['record_sha256'],'agent_id':self.binder.settings['agent'],'session_id':ctx['sessionId'],'session_key':ctx['sessionKey'],'channel':ctx['channel'],'conversation_identity':ctx['conversationRef'],'mime':'application/json','selector_json':canon({'field':'original_user_text','start':0,'end':len(raw)})}
  existing=self.db.execute('select * from source where source_id=?',(sid,)).fetchone()
  if existing:
   for key in ('content_sha256','source_event_sha256','record_sha256','session_id','conversation_identity'):
    if existing[key]!=row[key]:raise Denied('source_observation_conflict')
  else:self.db.execute('insert into source ('+','.join(row)+') values ('+','.join('?' for _ in row)+')',list(row.values()))
  return sid
 def duplicate_image_finance(self,record):
  hashes={a['sha256'] for a in record.get('attachments',[]) if a.get('status')=='preserved' and a.get('mime','').startswith('image/') and a.get('sha256')}
  if not hashes:return None
  found=[];visible=[]
  for row in self.db.execute("SELECT DISTINCT r.item_id,r.visibility,s.locator_json FROM current_item r JOIN financial_detail f USING(revision_id) JOIN evidence e USING(revision_id) JOIN source s USING(source_id)"):
   if any(a.get('sha256') in hashes for a in json.loads(row['locator_json']).get('attachments',[])):
    found.append(row['item_id'])
    if row['visibility']=='private':visible.append(row['item_id'])
  return {'visible_item_ids':sorted(set(visible))} if found else None
 def guard_new_time(self,p,raw,old=None):
  before=self.snapshot(old) if old else {}
  changed=[]
  for key in ('valid_from','valid_to'):
   if p.get(key) and p.get(key)!=before.get(key):changed.append((key,p[key],p.get('time_expression')))
  for detail,key,expression in [('financial','occurred_date','time_expression'),('schedule','start_date','time_expression'),('schedule','end_date','time_expression'),('task','due_date','due_expression')]:
   data=p.get(detail,{})
   if data.get(key) and data[key]!=before.get(detail,{}).get(key):changed.append((detail+'.'+key,data[key],data.get(expression) or p.get('time_expression')))
  for field,value,expression in changed:
   if expression and expression not in raw:raise ValueError('time expression must preserve original user wording; message date is not event date')
   # Undated speech is retained undated. This checks source support, not a model's date assertion.
   if not expression and not re.search(r'今天|明天|后天|昨天|前天|上周|下周|本周|周[一二三四五六日天末]|\d{4}[-年/]\d{1,2}[-月/]\d{1,2}|\d{1,2}月\d{1,2}|\d{1,2}[日号]',raw):raise ValueError('event date requires an explicit source time expression')
 def guards(self,p,quote):
  p=dict(p)
  if any(x in quote for x in ('可能','好像','也许','未确认','还没确认','听说')) and p.get('certainty','stated')=='stated':raise ValueError('uncertain source requires uncertain certainty')
  if '听说' in quote and not (p.get('assertion_kind')=='third_party_report' or (p.get('kind','record')=='record' and p.get('assertion_kind')=='unconfirmed' and p.get('certainty') in ('uncertain','unknown'))):raise ValueError('hearsay must retain attribution')
  if '我觉得' in quote and p.get('assertion_kind') not in ('user_judgment','user_feeling','unconfirmed'):raise ValueError('subjective source requires subjective assertion')
  if any(x in quote for x in ('计划','打算','准备')) and p.get('temporal_status')=='occurred':raise ValueError('plan cannot become occurred fact')
  if any(x in quote for x in ('私人','秘密','敏感')):p['visibility']='restricted'
  if p.get('task',{}).get('state')=='open' and any(x in quote for x in ('可能','好像','也许','未确认','还没确认','听说','不确定')):raise ValueError('uncertain intention is not an open task')
  if CANONICAL.get(p.get('domain'))=='life' and re.search('体检|就医|检验报告|症状|用药|头疼|头痛|腹痛|血压|血糖|服药',p.get('body','')):raise ValueError('health content may not be classified as life; use health or uncertain unclassified')
  if CANONICAL.get(p.get('domain'))=='unclassified' and self.health_intent(p.get('body','')):p['visibility']='restricted'
  if CANONICAL.get(p.get('domain'))=='health':
   p['visibility']='restricted'
   if p.get('assertion_kind')!='ai_inference' and p.get('body') and p['body'] not in quote:raise ValueError('health body must preserve original wording; AI interpretation requires separate uncertain inference')
  p['extraction']={'method':'host_bound_tool','model':None}
  return p
 def cancel_schedule(self,p,h,patch,b):
  old=self.snapshot(h)
  if 'schedule' not in old:return p
  wants_cancel=patch.get('status')=='deleted' or patch.get('task',{}).get('state')=='cancelled'
  if not wants_cancel:
   if 'task' in patch and 'task' not in old:raise ValueError('schedule update may not create a task')
   return p
  raw=b['text']
  if not re.search(r'取消|撤销|cancel',raw,re.I) or re.search(r'不要取消|不取消|别取消|不要撤销',raw):raise ValueError('schedule cancellation requires explicit instruction')
  if h['item_id'] not in raw:
   candidates=[]
   for row in self.db.execute("SELECT r.* FROM item i JOIN revision r ON i.head_revision_id=r.revision_id JOIN schedule_detail s USING(revision_id) WHERE r.status='active'"):
    if row['title'] and row['title'] in raw:candidates.append(row['item_id'])
   if candidates!=[h['item_id']]:raise ValueError('ambiguous schedule cancellation; query candidates and request exact item ID')
  p['status']='deleted';p['payload']={**old.get('payload',{}),'schedule_state':'cancelled'}
  # The schedule and immutable history remain; no task is manufactured to represent cancellation.
  p.pop('task',None)
  return p
 def commit(self,tool,args,b,r):
  self.validate(tool,args)
  sid=b['archive_event_id'];sensitive=any(w in b['text'] for w in ('私人','秘密','敏感'));key=tool+':'+sid+((':'+args['item_id']) if tool=='nexus_update' else '')
  rh=digest(canon(args));self.db.execute('begin immediate')
  try:
   prior=self.db.execute('select * from operation where operation_key=?',(key,)).fetchone()
   if prior:
    if prior['request_sha256']!=rh:raise Conflict('operation_key_request_hash_conflict')
    result=self.receipt(json.loads(prior['result_json']));result['idempotent']=True;self.db.execute('commit');return result
   if tool=='nexus_save' and any(p.get('financial') for p in args['proposals']):
    duplicates=self.duplicate_image_finance(r)
    if duplicates:
     self.db.execute('rollback');return {'status':'duplicate_attachment','committed':False,'existing_item_ids':duplicates['visible_item_ids'],'message':'原图已在Archive保留；相同图片已关联有效财务记录，本次未重复入账。若为纠错请更新原记录。'}
   self.source(b,r)
   results=[]
   if tool=='nexus_save':
    if re.search(r'取消.*(?:日程|行程|安排)|(?:日程|行程|安排).*取消',b['text']) and any(p.get('task',{}).get('state')=='cancelled' for p in args['proposals']):raise ValueError('cancel original schedule with nexus_update; do not save a cancellation task')
    origin=self.db.execute('select * from origin_item where archive_event_id=?',(sid,)).fetchone()
    for index,proposal in enumerate(args['proposals']):
     p=dict(proposal);quote=p.pop('quote',None) or b['text'];ev=self.evidence(sid,quote);p=self.guards(p,quote)
     self.guard_new_time(p,quote)
     image_hashes=[a['sha256'] for a in r.get('attachments',[]) if a.get('status')=='preserved' and a.get('mime','').startswith('image/') and a.get('sha256')]
     if image_hashes:p['payload']={**p.get('payload',{}),'image_derived_extraction':{'method':'normal_reply_vision','original_image_sha256':image_hashes,'caption_source_id':sid,'derived_not_original_bytes':True}}
     if sensitive:p['visibility']='restricted'
     p=self.prepare_group(p,b)
     p=self.prepare_summary(p,b)
     if index==0 and origin:
      if not origin['is_fallback']:raise Conflict('source already structured')
      h=self.head(origin['item_id']);res=self.insert_revision(p,[ev],item_id=h['item_id'],expected_revision=h['revision_id'],action='update')
      self.db.execute('update origin_item set is_fallback=0 where archive_event_id=?',(sid,))
     else:
      res=self.insert_revision(p,[ev])
      if index==0:self.db.execute('insert into origin_item values(?,?,?,0)',(sid,sid,res['item_id']))
     self.change_context(p,res['item_id'],b,sid)
     results.append(res)
   else:
    h=self.head(args['item_id']);
    if CANONICAL.get(h['domain'])=='health' and not getattr(self,'_health_access',False):raise Denied('explicit_health_request_required')
    p=self.snapshot(h);p.update(args['patch']);p=self.cancel_schedule(p,h,args['patch'],b);quote=p.pop('quote',None) or b['text'];p['reason']=args['reason'];p=self.guards(p,quote);self.guard_new_time(p,quote,old=h)
    if h['visibility']=='restricted' or sensitive:p['visibility']='restricted'
    p=self.prepare_group(p,b,old=h)
    p=self.prepare_summary(p,b)
    ev=[dict(e) for e in self.db.execute('select source_id,role,quote,start_char,end_char from evidence where revision_id=?',(h['revision_id'],))]
    ev.append(self.evidence(sid,quote,'corrects'))
    if p.get('summary_for_group'):ev=[self.evidence(sid,quote,'corrects')]  # Previous requests remain in the immutable parent chain; manifest binds every current member.
    results=[self.insert_revision(p,ev,item_id=h['item_id'],expected_revision=args['expected_revision'],action='soft_delete' if p.get('status')=='deleted' else 'correction')]
    self.change_context(p,h['item_id'],b,sid)
   result={'status':'saved','committed':True,'results':results,'source_id':sid,'operation_key':key}
   result=self.receipt(result)
   self.db.execute('insert into operation values(?,?,?,?,?)',(key,rh,self.binder.settings['agent'],canon(result),now()));self.db.execute('commit');return result
  except BaseException:
   self.db.execute('rollback');raise
 def snapshot(self,h):
  p={k:h[k] for k in PROPOSAL if k in h};p['tags']=json.loads(h['tags_json']);p['payload']=json.loads(h['payload_json'])
  p['relations']=[{'subject_item_id':r['subject_item_id'],'object_item_id':r['object_item_id'],'predicate':r['predicate'],'qualifiers':json.loads(r['qualifiers_json'])} for r in self.db.execute('select * from relation where revision_id=?',(h['revision_id'],))]
  p['aliases']=[r[0] for r in self.db.execute('select alias from entity_alias where revision_id=?',(h['revision_id'],))]
  for name in ('task','financial','schedule'):
   row=self.db.execute('select * from '+name+'_detail where revision_id=?',(h['revision_id'],)).fetchone()
   if row:p[name]={k:row[k] for k in row.keys() if k!='revision_id'}
  return p
 def fallback(self,b,r):
  sid=b['archive_event_id'];self.db.execute('begin immediate')
  try:
   origin=self.db.execute('select item_id from origin_item where archive_event_id=?',(sid,)).fetchone()
   if origin:
    result=self.receipt({'status':'saved','committed':True,'item_id':origin[0],'idempotent':True});self.db.execute('commit');return result
   self.source(b,r);raw=b['text'];p={'kind':'record','title':'明确记录原话','body':raw[:8000],'domain':'unclassified','assertion_kind':'unconfirmed','certainty':'unknown','temporal_status':'unknown','visibility':'restricted' if any(x in raw for x in ('私人','秘密','敏感')) else 'private','extraction':{'method':'L0_verbatim_no_llm'}}
   if '工作随手记' in raw:p['domain']='work'
   elif self.health_intent(raw):p.update(domain='health',visibility='restricted')
   elif '生活随手记' in raw:p['domain']='life'
   p=self.prepare_group(p,b,fallback=True)
   res=self.insert_revision(p,[self.evidence(sid)],actor='L0');self.db.execute('insert into origin_item values(?,?,?,1)',(sid,sid,res['item_id']))
   result=self.receipt({'status':'saved','committed':True,**res});self.db.execute('insert into operation values(?,?,?,?,?)',('fallback:'+sid,digest(raw),'L0',canon(result),now()));self.db.execute('commit');return result
  except BaseException:self.db.execute('rollback');raise
 def enqueue(self,tool,args,ctx,b=None):
  key=digest(canon([tool,ctx.get('sessionId'),ctx.get('toolCallId') or ctx.get('sourceEventId'),args]))
  old=self.db.execute('select status,result_json from pending_intent where intent_id=?',(key,)).fetchone()
  if old and old['status']=='completed':return json.loads(old['result_json'])
  if self.db.execute("select count(*) from pending_intent where status='pending'").fetchone()[0]>=1000:raise ValueError('pending queue full')
  self.db.execute("insert or ignore into pending_intent(intent_id,kind,ctx_json,args_json,binding_json,status,next_at,created_at) values(?,?,?,?,?,'pending',?,?)",(key,tool,canon(ctx),canon(args),canon(b) if b else None,time.time(),time.time()))
  return {'status':'pending_source','committed':False,'intent_id':key,'message':'尚未保存，等待原始来源核验；可查询 pending_status。'}
 def reconcile(self):
  for row in self.db.execute("select * from pending_intent where status='pending' and next_at<=? order by created_at limit 25",(time.time(),)).fetchall():
   try:
    if time.time()-row['created_at']>72*3600 or row['attempts']>=30:raise Denied('pending_retry_exhausted')
    ctx=json.loads(row['ctx_json']);b=self.binder.native(ctx)
    if row['binding_json']:
     old=json.loads(row['binding_json'])
     if old['event_sha256']!=b['event_sha256']:raise Denied('pending_source_changed')
    r=self.binder.archive(b);args=json.loads(row['args_json']);result=self.fallback(b,r) if row['kind']=='fallback' else self.commit(row['kind'],args,b,r)
    self.db.execute("update pending_intent set status='completed',result_json=?,ctx_json='{}',args_json='{}',binding_json=NULL,last_error=NULL where intent_id=?",(canon(result),row['intent_id']))
   except (Pending,sqlite3.OperationalError) as e:
    self.db.execute('update pending_intent set attempts=attempts+1,next_at=?,last_error=? where intent_id=?',(time.time()+min(3600,2**min(row['attempts']+1,11)),type(e).__name__+':'+str(e)[:100],row['intent_id']))
   except Exception as e:self.db.execute("update pending_intent set status='failed',last_error=? where intent_id=?",(type(e).__name__+':'+str(e)[:100],row['intent_id']))
  # Retain bounded terminal audit; operation remains immutable.
  self.db.execute("delete from pending_intent where intent_id in(select intent_id from pending_intent where status!='pending' order by created_at desc limit -1 offset 1000)")
 def _legacy_filtered_search(self,args):
  if not any(args.get(x) for x in ('tag','status','entity')):return self.search(args.get('text',''),args.get('domain'),args.get('start'),args.get('end'),args.get('limit',10),4000)
  limit=args.get('limit',10)
  if not isinstance(limit,int) or not 1<=limit<=20 or len(args.get('text',''))>200:raise ValueError('search budget')
  where=["r.visibility='private'","r.status=?"];params=[args.get('status','active')]
  if params[0] not in ('active','review','deleted'):raise ValueError('status invalid')
  for key,col in [('domain','domain'),('start','valid_from'),('end','valid_from')]:
   if args.get(key):where.append('r.'+col+('>=?' if key=='start' else '<?' if key=='end' else '=?'));params.append(args[key])
  if args.get('text'):where.append('instr(r.title||r.body,?)>0');params.append(args['text'])
  if args.get('tag'):where.append('exists(select 1 from json_each(r.tags_json) where value=?)');params.append(args['tag'])
  if args.get('entity'):where.append('exists(select 1 from relation where revision_id=r.revision_id and object_item_id=?)');params.append(args['entity'])
  self.db.set_progress_handler(lambda:1,2000000)
  try:rows=self.db.execute('select r.* from item i join revision r on i.head_revision_id=r.revision_id where '+' and '.join(where)+' order by r.created_at desc limit ?',params+[limit+1]).fetchall()
  finally:self.db.set_progress_handler(None,0)
  hits=[];size=0
  for row in rows[:limit]:
   hit={k:row[k] for k in ('item_id','revision_id','title','domain','assertion_kind','certainty','temporal_status')};hit['excerpt']=row['body'][:320];hit['source_ids']=[e[0] for e in self.db.execute('select source_id from evidence where revision_id=? limit 5',(row['revision_id'],))]
   size+=len(canon(hit))
   if size>4000:break
   hits.append(hit)
  return {'hits':hits,'truncated':len(hits)<len(rows),'coverage':'matching_current_records_only'}
 def archive_history(self,args):
  if set(args)-{'template','name','limit'}:raise ValueError('archive history only accepts name and limit')
  needle=args.get('name');limit=args.get('limit',3)
  if not isinstance(needle,str) or not 2<=len(needle)<=100:raise ValueError('bounded keyword required')
  if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=3:raise ValueError('history limit 1..3')
  root=Path(self.binder.settings['archiveRoot']);hits=[];matched=0;invalid=0
  for path in sorted((root/'conversations').glob('*/*/*/*.json'),reverse=True):
   record=json.loads(path.read_bytes());meta=record.get('source_event',{}).get('message',{}).get('__openclaw',{});channel=record.get('channel')
   if record.get('agent_id')!=self.binder.settings['agent'] or record.get('role')!='user' or meta.get('senderIsOwner') is not True or meta.get('senderId') not in self.binder.settings['owners'].get(channel,[]):continue
   raw=record.get('original_user_text','')
   if self.health_intent(raw) and not getattr(self,'_health_access',False):continue
   if any(x in raw for x in ('私人','秘密','敏感')):continue
   if self.db.execute("SELECT 1 FROM current_item r JOIN evidence e USING(revision_id) WHERE e.source_id=? AND r.visibility='restricted' LIMIT 1",(record.get('archive_event_id'),)).fetchone():continue
   c=self.binder.db()
   try:conv=c.execute('select kind,account_id,channel from conversations where conversation_id=?',(record.get('conversation_identity'),)).fetchone()
   finally:c.close()
   if not conv or tuple(conv)!=('direct',self.binder.settings['account'],channel):continue
   if needle.casefold() not in raw.casefold():continue
   if digest(canon({k:v for k,v in record.items() if k!='record_sha256'}))!=record.get('record_sha256') or digest(canon(record.get('source_event')))!=record.get('source_event_sha256'):
    invalid+=1;continue
   matched+=1
   if len(hits)<limit:
    # Original excerpt, never a Memory summary; return no internal filesystem paths.
    start=max(0,raw.casefold().find(needle.casefold())-200);end=min(len(raw),start+1000)
    hits.append({'archive_event_id':record['archive_event_id'],'source_event_id':record['source_event_id'],'channel':channel,'original_timestamp':record['original_timestamp'],'original_excerpt':raw[start:end],'excerpt_start':start,'excerpt_end':end,'text_truncated':start>0 or end<len(raw),'source_event_sha256':record['source_event_sha256'],'record_sha256':record['record_sha256'],'original_verified':True})
  return {'hits':hits,'total_matching_verified_owner_sources':matched,'returned':len(hits),'partial_expansion':len(hits)<matched or any(x['text_truncated'] for x in hits),'invalid_matching_sources':invalid,'scope':'preserved authorized-agent original owner user messages on currently authorized channels only','not_found_means':'未找到，不能推断从未说过；关键词/来源范围有限','char_budget':3000}
 def source_view(self,sid):
  row=self.db.execute('select * from source where source_id=?',(sid,)).fetchone()
  locator=json.loads(row['locator_json']);integrity={'stored_text_sha256_matches':digest(row['raw_text'])==row['content_sha256'],'original_verified':False}
  images=[]
  if row['namespace']=='archive':
   archive_id=row['archive_event_id']
   if isinstance(archive_id,str) and re.fullmatch('ocarc1_[0-9a-f]{64}',archive_id):
    root=Path(self.binder.settings['archiveRoot'])
    matches=list((root/'conversations').glob('*/*/*/'+archive_id+'.json'))
    if len(matches)==1:
     record=json.loads(matches[0].read_bytes())
     integrity['original_verified']=digest(canon({k:v for k,v in record.items() if k!='record_sha256'}))==row['record_sha256'] and record.get('record_sha256')==row['record_sha256'] and digest(canon(record.get('source_event')))==row['source_event_sha256']
     for a in record.get('attachments',[]):
      sha=a.get('sha256');ok=False
      if a.get('status')=='preserved' and isinstance(sha,str) and re.fullmatch('[0-9a-f]{64}',sha):
       obj=root/'attachments/objects'/sha[:2]/sha
       if obj.is_file():
        import hashlib
        ok=hashlib.sha256(obj.read_bytes()).hexdigest()==sha
      images.append({'sha256':sha,'mime':a.get('mime'),'bytes_verified':ok,'status':a.get('status')})
  if row['namespace']=='legacy':
   from legacy_source import integrity as legacy_integrity
   integrity.update(legacy_integrity(row,self.binder.settings))
   for a in locator.get('attachments',[]):
    sha=a.get('sha256');obj=Path(self.binder.settings['archiveRoot'])/'attachments/objects'/str(sha)[:2]/str(sha);ok=isinstance(sha,str) and bool(re.fullmatch('[0-9a-f]{64}',sha)) and obj.is_file() and __import__('hashlib').sha256(obj.read_bytes()).hexdigest()==sha
    images.append({'sha256':sha,'mime':a.get('mime'),'bytes_verified':ok,'status':a.get('status')})
  withheld=self.health_intent(row['raw_text']) and not getattr(self,'_health_access',False)
  return {'source_id':sid,'namespace':row['namespace'],'health_text_withheld':withheld,'text':'' if withheld else row['raw_text'][:1000],'text_truncated':len(row['raw_text'])>1000,'content_sha256':row['content_sha256'],'file_sha256':row['file_sha256'],'source_event_sha256':row['source_event_sha256'],'record_sha256':row['record_sha256'],'integrity':integrity,'attachments':images}
 def execute(self,tool,args,ctx):
  self.validate(tool,args);self.binder.authorize(ctx)
  b=None
  try:
   b=self.binder.native(ctx)
   self._health_access=self.health_intent(b['text'])
   if tool in ('nexus_save','nexus_update'):return self.commit(tool,args,b,self.binder.archive(b))
  except Pending:
   if tool in ('nexus_save','nexus_update'):return self.enqueue(tool,args,ctx,b)
   return {'status':'pending_source','committed':False}
  if tool=='nexus_search':
   return self.decorate_hits(self.filtered_search(args))
  if tool=='nexus_query':
   if args.get('template')=='archive_history':return self.archive_history(args)
   if args.get('template') in ('group_snapshots','group_audit','group_snapshot_members'):return self.completion_query(args,b)
   if args.get('template','').startswith('group_'):return self.group_query(args,b)
   if args.get('template')=='pending_status':return {'intents':[dict(r) for r in self.db.execute('select intent_id,status,attempts,last_error,result_json from pending_intent order by created_at desc limit 10')]}
   if args.get('template') in ('records_by_period','domain_summary_candidates','unclassified_records','upcoming_schedules'):return self.period_query(args)
   if args.get('template') in ('trip_costs','financial_totals'):return self.financial_query(args)
   return self.query(args['template'],start=args.get('start'),end=args.get('end'),entity_id=args.get('entity_id'))
  if tool in ('nexus_get_source','nexus_delete_preview'):
   h=self.head(args['item_id'])
   if h['visibility']=='restricted' and not (CANONICAL.get(h['domain'])=='health' and getattr(self,'_health_access',False)):raise Denied('restricted_not_available_via_ordinary_tools')
   if tool=='nexus_delete_preview':return self.delete_preview(args['item_id'])
   ids=[e[0] for e in self.db.execute('select source_id from evidence where revision_id=? limit 5',(h['revision_id'],))]
   if args.get('source_id') and args['source_id'] not in ids:raise Denied('source_not_bound_to_item')
   if args.get('source_id'):ids=[args['source_id']]
   return {'sources':[self.source_view(sid) for sid in ids[:3]],'truncated':True,'char_budget':3000}
