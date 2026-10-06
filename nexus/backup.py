"""Verified online SQLite recovery points. Independent from Git and model calls."""
import os,json,time,sqlite3,fcntl,uuid,shutil
from pathlib import Path
from base import canon,now

def verified_backup(n,root,periodic=False):
 root=Path(root);folder=root/'backups'/('periodic' if periodic else 'manual-verified');folder.mkdir(parents=True,exist_ok=True);os.chmod(folder,0o700)
 lock=open(folder/'backup.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 name='nexus-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
 temp=folder/(name+'.pending');target=folder/(name+'.sqlite3');dest=sqlite3.connect(temp)
 try:
  n.db.backup(dest);check=dest.execute('pragma quick_check').fetchone()[0];dest.close()
  if check!='ok':raise ValueError('backup quick_check failed')
  from core import Core
  clone=Core(temp,n.binder.settings)
  try:verify=clone.verify()
  finally:clone.close()
  if verify['errors']:raise ValueError('backup verify failed')
  # Core closes its WAL connection; this standalone snapshot needs no live WAL.
  temp.chmod(0o600);temp.replace(target)
  result={'status':'ok','path':str(target),'created_at':now(),'checked_at':time.time(),'quick_check':check,'verify':verify,'method':'sqlite_backup_api','retention':{'interval_seconds':86400,'keep_latest':30} if periodic else None}
  (folder/(name+'.json')).write_text(canon(result))
  if periodic:
   for old in sorted(folder.glob('nexus-*.sqlite3'),key=lambda p:p.stat().st_mtime,reverse=True)[30:]:
    # Only exact artifacts created by this routine are eligible for retention.
    receipt=old.with_suffix('.json')
    if receipt.exists() and json.loads(receipt.read_text()).get('method')=='sqlite_backup_api':old.unlink();receipt.unlink()
  return result
 except BaseException:
  dest.close()
  if temp.exists():temp.unlink()
  raise
 finally:lock.close()

def maybe_backup(n,root):
 root=Path(root);state=root/'state/periodic-backup.json';t=time.time();previous=json.loads(state.read_text()) if state.exists() else {}
 next_at=previous.get('next_at',0)
 if t<next_at:return previous
 try:result=verified_backup(n,root,True);result['next_at']=t+86400
 except Exception as e:result={'status':'failed','checked_at':t,'error':type(e).__name__,'next_at':t+3600,'last_success_at':previous.get('checked_at') if previous.get('status')=='ok' else previous.get('last_success_at')}
 temp=state.with_suffix('.json.tmp');temp.write_text(canon(result));temp.chmod(0o600);temp.replace(state);return result
