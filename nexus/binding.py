"""Trusted runtime context + exact transcript ancestry; Archive is read-only."""
import hashlib,json,sqlite3,re
from transcript import decode_event
from pathlib import Path

def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(v):return hashlib.sha256(v.encode() if isinstance(v,str) else v).hexdigest()
def message_text(e):
 m=e.get('message',{});meta=m.get('__openclaw',{})
 if isinstance(meta.get('upstreamUserText'),str):return meta['upstreamUserText']
 c=m.get('content',[])
 return c if isinstance(c,str) else '\n'.join(b['text'] for b in c if isinstance(b,dict) and isinstance(b.get('text'),str))

class Denied(ValueError):pass
class Pending(ValueError):pass

def matches_tool_anchor(block, call):
 if not isinstance(block,dict) or block.get('type') not in ('toolCall','toolUse'):return False
 if block.get('id')==call:return True
 # OpenClaw Tool Search executes a nested tool with a host-generated ID.
 # Bind it to the exact persisted outer call and target; never use the latest message.
 if block.get('name')!='tool_call' or not isinstance(block.get('id'),str):return False
 args=block.get('arguments',block.get('input'))
 if isinstance(args,str):
  try:args=json.loads(args)
  except (ValueError,TypeError):return False
 if not isinstance(args,dict):return False
 target=args.get('id',args.get('toolId',args.get('name')))
 if not isinstance(target,str):return False
 target=target.strip()
 if target not in ('nexus_save','nexus_update','nexus_search','nexus_query','nexus_get_source','nexus_delete_preview'):return False
 outer=re.sub(r'[^A-Za-z0-9_.:-]+','_',block['id'].strip())[:120] or 'call'
 prefix='tool_call:'+outer+':'+target+':'
 return isinstance(call,str) and call.startswith(prefix) and bool(re.fullmatch(r'[1-9][0-9]*',call[len(prefix):]))

class Binder:
 def __init__(self,settings):self.settings=settings
 def authorize(self,ctx):
  channel=ctx.get('channel');sender=ctx.get('requesterSenderId')
  if ctx.get('agentId')!=self.settings['agent'] or ctx.get('accountId')!=self.settings['account'] or ctx.get('senderIsOwner') is not True or channel not in ('telegram','wecom') or sender not in self.settings['owners'].get(channel,[]):raise Denied('owner_private_only')
  if not isinstance(ctx.get('sessionKey'),str) or not ctx['sessionKey'].startswith('agent:'+self.settings['agent']+':') or any(x in ctx['sessionKey'] for x in (':cron:',':heartbeat:',':subagent:')):raise Denied('session_not_allowed')
  if not ctx.get('sessionId'):raise Denied('missing_session_identity')
 def db(self):
  c=sqlite3.connect(Path(self.settings['sourceDB']).resolve().as_uri()+'?mode=ro',uri=True,timeout=1);c.row_factory=sqlite3.Row;c.execute('pragma query_only=on');return c
 def native(self,ctx):
  self.authorize(ctx);c=self.db();c.execute("begin")
  try:
   w=c.execute('select session_key from session_windows where session_id=?',(ctx['sessionId'],)).fetchone()
   if not w or w['session_key']!=ctx['sessionKey']:raise Denied('session_identity_mismatch')
   events={}
   for row in c.execute('select * from transcript_events where session_id=?',(ctx['sessionId'],)):
    e=decode_event(row);events[e.get('id')]=(row['seq'],e)
   if ctx.get('sourceEventId'):
    # Only worker-generated exact transcript notification, never model parameters.
    pair=events.get(ctx['sourceEventId'])
    if not pair:raise Pending('source_not_persisted')
    seq,event=pair
   else:
    call=ctx.get('toolCallId')
    if not call:raise Denied('missing_host_tool_call_identity')
    found=[]
    for _,e in events.values():
     content=e.get('message',{}).get('content',[])
     if e.get('message',{}).get('role')=='assistant' and isinstance(content,list) and any(matches_tool_anchor(b,call) for b in content):found.append(e)
    if len(found)>1:raise Denied('ambiguous_tool_anchor')
    if not found:raise Pending('tool_anchor_not_yet_persisted')
    event=found[0];visited=set()
    while event.get('message',{}).get('role')!='user':
     if event.get('id') in visited:raise Denied('parent_cycle')
     visited.add(event.get('id'));pair=events.get(event.get('parentId'))
     if not pair:raise Pending('parent_not_yet_persisted')
     seq,event=pair
    if ctx.get('admissionId') and ctx['admissionId'] not in (event.get('id'),event.get('message',{}).get('idempotencyKey')):raise Denied('admission_identity_mismatch')
   m=event.get('message',{});meta=m.get('__openclaw',{});t=meta.get('transport',{})
   if m.get('role')!='user' or meta.get('senderIsOwner') is not True or meta.get('senderId')!=ctx['requesterSenderId'] or t.get('channel')!=ctx['channel']:raise Denied('source_requester_mismatch')
   conv=c.execute('select * from conversations where conversation_id=?',(t.get('conversationRef'),)).fetchone()
   if not conv or conv['kind']!='direct' or conv['account_id']!=self.settings['account'] or conv['channel']!=ctx['channel']:raise Denied('not_private_conversation')
   if ctx.get('conversationRef') and ctx['conversationRef']!=conv['conversation_id']:raise Denied('conversation_identity_mismatch')
   # A host-supplied native target is checked against exact known conversation fields.
   target=ctx.get('nativeChannelId')
   if target and str(target) not in {str(conv[k]) for k in ('native_channel_id','native_direct_user_id','peer_id','delivery_target')}:
    raise Denied('native_conversation_mismatch')
   raw_hash=sha(canonical(event));logical=sha(canonical([self.settings['agent'],ctx['sessionId'],event.get('id') or seq]));archive_id='ocarc1_'+sha(canonical([logical,raw_hash]))
   return {'ctx':{**ctx,'conversationRef':conv['conversation_id']},'event':event,'event_sha256':raw_hash,'archive_event_id':archive_id,'text':message_text(event),'seq':seq}
  finally:c.close()
 def archive(self,binding):
  event=binding['event'];ts=event.get('timestamp') or event.get('message',{}).get('timestamp')
  import datetime as dt
  try:date=(dt.datetime.fromtimestamp(ts/1000,dt.timezone.utc) if isinstance(ts,(int,float)) else dt.datetime.fromisoformat(ts.replace('Z','+00:00'))).date().isoformat()
  except Exception:raise Denied('source_timestamp_invalid')
  root=Path(self.settings['archiveRoot']);p=root/'conversations'/date[:4]/date[5:7]/date[8:10]/(binding['archive_event_id']+'.json')
  if not p.is_file():raise Pending('pending_source')
  r=json.loads(p.read_bytes());expected=sha(canonical({k:v for k,v in r.items() if k!='record_sha256'}))
  if r.get('record_sha256')!=expected or r.get('source_event_sha256')!=binding['event_sha256'] or sha(canonical(r.get('source_event')))!=binding['event_sha256'] or r.get('source_event')!=event:raise Denied('archive_hash_mismatch')
  ctx=binding['ctx']
  if r.get('archive_event_id')!=binding['archive_event_id'] or r.get('agent_id')!=self.settings['agent'] or r.get('session_id')!=ctx['sessionId'] or r.get('channel')!=ctx['channel'] or r.get('conversation_identity')!=ctx['conversationRef']:raise Denied('archive_identity_mismatch')
  for attachment in r.get('attachments',[]):
   if attachment.get('status')!='preserved':continue
   digest=attachment.get('sha256')
   if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise Denied('attachment_hash_invalid')
   obj=root/'attachments/objects'/digest[:2]/digest
   if not obj.is_file() or sha(obj.read_bytes())!=digest:raise Denied('attachment_bytes_hash_mismatch')
  return r
