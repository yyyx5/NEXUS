"""Local bounded CLI and worker; no network and no generation/embedding calls."""
import argparse,json,os,time,sys,sqlite3,fcntl,signal
from pathlib import Path
from core import Core,PREFIX,canon
from binding import message_text,Denied,Pending
from transcript import decode_event
from backup import verified_backup,maybe_backup

def scan(n,initialize=False):
 c=n.binder.db()
 try:
  for w in c.execute('select session_id,session_key from session_windows'):
   ck=n.db.execute('select seq from worker_checkpoint where session_id=?',(w['session_id'],)).fetchone()
   if ck is None:
    # An explicit installation watermark prevents historical auto-structuring.
    top=c.execute('select coalesce(max(seq),0) from transcript_events where session_id=?',(w['session_id'],)).fetchone()[0] if initialize else 0
    n.db.execute('insert into worker_checkpoint values(?,?)',(w['session_id'],top));ck=(top,)
   for row in c.execute('select * from transcript_events where session_id=? and seq>? order by seq limit 200',(w['session_id'],ck[0])):
    e=decode_event(row);m=e.get('message',{});meta=m.get('__openclaw',{});t=meta.get('transport',{})
    if m.get('role')=='user' and PREFIX.search(message_text(e)):
     ctx={'agentId':n.binder.settings['agent'],'sessionId':w['session_id'],'sessionKey':w['session_key'],'accountId':n.binder.settings['account'],'channel':t.get('channel'),'requesterSenderId':meta.get('senderId'),'senderIsOwner':meta.get('senderIsOwner'),'sourceEventId':e.get('id'),'conversationRef':t.get('conversationRef')}
     try:
      b=n.binder.native(ctx)
      try:n.fallback(b,n.binder.archive(b))
      except Pending:n.enqueue('fallback',{},ctx,b)
     except Denied:pass
    # Errors other than denied are deliberately retried without advancing checkpoint.
    n.db.execute('update worker_checkpoint set seq=? where session_id=?',(row['seq'],w['session_id']))
 finally:c.close()
def main():
 os.umask(0o077);p=argparse.ArgumentParser();p.add_argument('command',choices=['call','worker','init','verify','backup']);p.add_argument('--root',required=True);a=p.parse_args();root=Path(a.root).resolve();settings=json.loads((root/'state/settings.json').read_text());n=Core(root/'data/nexus.sqlite3',settings)
 if a.command=='call':
  request=json.loads(sys.stdin.readline(100000));
  try:result=n.execute(request['tool'],request['args'],request['ctx'])
  except Exception as e:result={'status':'error','committed':False,'error':type(e).__name__,'reason':str(e)[:150],'message':'Nexus 未保存；正常聊天可继续。'}
  print(canon(result));n.close();return
 if a.command=='verify':print(canon(n.verify()));n.close();return
 if a.command=='backup':
  print(canon(verified_backup(n,root)));n.close();return
 if a.command=='init':scan(n,initialize=True);n.close();print('{"initialized":true}');return
 lock=open(root/'state/worker.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);(root/'state/worker.pid').write_text(str(os.getpid()))
 running=True
 def stop(*args):
  nonlocal running;running=False
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 import select
 while running:
  try:
   if not (root/'state/PAUSED').exists():scan(n);n.reconcile()
   backup_status=maybe_backup(n,root) if not (root/'state/PAUSED').exists() else {}
   (root/'state/health.json').write_text(canon({'pid':os.getpid(),'checked_at':time.time(),'paused':(root/'state/PAUSED').exists(),'backup_status':backup_status.get('status'),'backup_next_at':backup_status.get('next_at'),'pending':n.db.execute("select count(*) from pending_intent where status='pending'").fetchone()[0]}))
  except Exception as e:
   (root/'state/last-error.json').write_text(canon({'at':time.time(),'error':type(e).__name__,'reason':str(e)[:150]}))
  ready,_,_=select.select([sys.stdin],[],[],2)
  if ready:
   line=sys.stdin.readline()
   if not line:time.sleep(2)
 n.close()
if __name__=='__main__':main()
