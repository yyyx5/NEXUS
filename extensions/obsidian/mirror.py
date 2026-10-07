"""Local-first mirror; no LLM, cloud API, or production service imports."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo
from . import read_view

REPO = Path(__file__).resolve().parents[2]
FOLDERS = ['01-时间线','02-旅行','03-生活','04-工作','05-人物','06-财务','07-健康','08-项目','09-未分类','99-系统']
MARKER = 'nexus-mirror-generated: v1'
MANIFEST = '.nexus-managed.json'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def overlaps(a, b):
    return a == b or a in b.parents or b in a.parents

def outside_repo(path):
    path = Path(path).expanduser().resolve()
    if overlaps(REPO, path):
        raise ValueError('Keep real configuration, databases and mirrors outside the source repository.')
    return path

def validate(config):
    if config.get('enabled') is not True:
        raise ValueError('The optional mirror is not enabled; run setup when you want it.')
    source = outside_repo(config['database'])
    if not source.is_file():
        raise ValueError('Nexus database does not exist.')
    local = outside_repo(config['local_vault'])
    cloud = outside_repo(config['icloud_vault']) if config.get('icloud_vault') else None
    for target in (local, cloud):
        if target is None:
            continue
        if target.name != 'Nexus':
            raise ValueError('Use a dedicated directory named Nexus for each mirror.')
        if target == source.parent or target in source.parents or source in target.parents:
            raise ValueError('A mirror must not overlap the source database directory.')
        safe(target, MANIFEST)
    if cloud and overlaps(local, cloud):
        raise ValueError('Local and iCloud mirrors must be separate, non-nested directories.')
    ZoneInfo(config.get('timezone', 'UTC'))
    if not isinstance(config.get('include_sensitive', False), bool):
        raise ValueError('include_sensitive must be a boolean.')
    return {**config, 'database': str(source), 'local_vault': str(local),
            'icloud_vault': str(cloud) if cloud else None}

def safe(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts or '.obsidian' in path.parts:
        raise ValueError('Unsafe generated path.')
    destination = root / path
    for part in (destination, *destination.parents):
        if part.is_symlink():
            raise ValueError('Symlinks are not accepted in generated paths.')
    return destination

def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.nexus-tmp-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def managed(root):
    path = safe(root, MANIFEST)
    if not path.exists():
        return {'format': 1, 'files': {}}
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('Unsupported generated-file manifest.')
    for relative in manifest['files']:
        safe(root, relative)
    return manifest

def reconcile(root, contents, metadata):
    safe(root, MANIFEST)
    old = managed(root)
    # All ownership and Markdown checks precede any publication/deletion.
    for relative, data in contents.items():
        destination = safe(root, relative)
        if not data.startswith(b'---\n') or MARKER.encode() not in data[:800] or not data.endswith(b'\n'):
            raise ValueError('Invalid generated Markdown.')
        if destination.exists():
            current = destination.read_bytes()
            if relative not in old['files'] and current != data:
                raise ValueError('An unowned file occupies a generated note path.')
            if MARKER.encode() not in current[:800]:
                raise ValueError('A file has lost its generated ownership marker.')
    for relative in old['files'].keys() - contents.keys():
        destination = safe(root, relative)
        if destination.exists() and MARKER.encode() not in destination.read_bytes()[:800]:
            raise ValueError('Refusing to delete a file without its generated marker.')
    for folder in FOLDERS:
        safe(root, folder).mkdir(parents=True, exist_ok=True)
    for relative, data in contents.items():
        destination = safe(root, relative)
        if not destination.exists() or destination.read_bytes() != data:
            atomic(destination, data)
    for relative in old['files'].keys() - contents.keys():
        destination = safe(root, relative)
        if destination.exists():
            destination.unlink()
    atomic(safe(root, MANIFEST), json.dumps({'format': 1, 'files': {k:digest(v) for k,v in contents.items()},
                                           **metadata}, ensure_ascii=False, indent=2).encode())

def page(title, body, fields=None):
    fields = dict(fields or {})
    fields.pop('source', None)
    frontmatter = '\n'.join(key+': '+json.dumps(value, ensure_ascii=False) for key,value in fields.items())
    return ('---\n'+MARKER+'\nsource: nexus\n'+(frontmatter+'\n' if frontmatter else '')+
            '---\n\n# '+title+'\n\n'+body.rstrip()+'\n').encode()

def folder(row, payload, financial):
    domain = row['domain'].lower()
    states = {str(payload.get(key, '')).lower() for key in ('status','classification_status','archive_status')}
    if row['status'] != 'active' or domain in ('unclassified','uncategorized','unknown','pending','未分类','待整理') or states & {'pending','unclassified','unfiled','待整理','待归档','未归档'}:
        return '09-未分类'
    base = {'life':'03-生活','生活':'03-生活','work':'04-工作','工作':'04-工作','health':'07-健康','健康':'07-健康',
            'travel':'02-旅行','旅行':'02-旅行','finance':'06-财务','财务':'06-财务',
            'project':'08-项目','项目':'08-项目','people':'05-人物','人物':'05-人物'}.get(domain)
    if base is None:
        return '09-未分类'
    if base == '07-健康':
        return base
    if financial:
        return '06-财务'
    tags = json.loads(row['tags_json'])
    if base == '03-生活' and any(t in ('旅行','travel','trip') or t.startswith('trip:itm_') for t in tags):
        return '02-旅行'
    return base

def status_page(status):
    labels = [('time','最近同步时间'),('local','Nexus → 本地'),('cloud','本地 → iCloud'),
              ('added','新增数量'),('updated','更新数量'),('removed','移除数量'),
              ('unclassified','未分类数量'),('errors','错误数量')]
    lines = ['- '+label+'：'+str(status.get(key,0)) for key,label in labels]
    if status.get('error'):
        lines.append('\n'+status['error'])
    return page('同步状态','\n'.join(lines)+'\n\niCloud成功仅表示本机容器写入/校验；设备端下载须自行确认。未分类统计仅覆盖本次允许导出的内容。')

def write_status(root, status):
    metadata = managed(root)
    relative = '99-系统/同步状态.md'
    data = status_page(status)
    destination = safe(root, relative)
    if destination.exists() and (relative not in metadata['files'] or MARKER.encode() not in destination.read_bytes()[:800]):
        raise ValueError('An unowned file occupies the status page.')
    atomic(destination, data)
    metadata['files'][relative] = digest(data)
    metadata['last_run'] = status
    atomic(safe(root, MANIFEST), json.dumps(metadata, ensure_ascii=False, indent=2).encode())

def cloud_step(config):
    config = validate(config)
    if not config.get('icloud_vault'):
        return
    local, cloud = Path(config['local_vault']), Path(config['icloud_vault'])
    metadata = managed(local)
    contents = {}
    for relative, checksum in metadata['files'].items():
        data = safe(local, relative).read_bytes()
        if digest(data) != checksum:
            raise ValueError('Local mirror changed during cloud copying.')
        contents[relative] = data
    reconcile(cloud, contents, {k:v for k,v in metadata.items() if k not in ('format','files')})
    for relative, data in contents.items():
        if digest(safe(cloud, relative).read_bytes()) != digest(data):
            raise ValueError('Cloud content verification failed.')
    status = {**metadata['last_run'], 'cloud':'成功', 'errors':0}
    status.pop('error', None)
    write_status(cloud, status)
    write_status(local, status)

def run(config, state_dir, local_only=False):
    if not config.get('enabled'):
        return {'skipped': True, 'reason': 'Optional visualization is disabled; setup can enable it later.'}
    config = validate(config)
    state_dir = outside_repo(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    local = Path(config['local_vault'])
    with (state_dir/'sync.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'skipped': True, 'reason': 'Another mirror run holds the lock.'}
        previous = managed(local)
        status = {'time':datetime.datetime.now(ZoneInfo(config.get('timezone','UTC'))).isoformat(timespec='seconds'),
                  'local':'失败', 'cloud':'未执行', 'added':0, 'updated':0, 'removed':0,
                  'unclassified':previous.get('unclassified',0), 'errors':0}
        try:
            contents, metadata = read_view.export(config, FOLDERS, folder, page)
            old = previous.get('items', {})
            status.update(local='成功', added=len(metadata['items'].keys()-old.keys()),
                          updated=sum(value != old[key] for key,value in metadata['items'].items() if key in old),
                          removed=len(old.keys()-metadata['items'].keys()), unclassified=metadata['unclassified'],
                          exported=len(metadata['items']), total=metadata['total'])
            status['cloud'] = '未启用' if not config.get('icloud_vault') else ('未执行（仅本地）' if local_only else '进行中')
            contents['99-系统/同步状态.md'] = status_page(status)
            with tempfile.TemporaryDirectory(prefix='staging-', dir=state_dir) as temporary:
                stage = Path(temporary)
                for relative,data in contents.items():
                    atomic(safe(stage,relative),data)
                checked = {relative:safe(stage,relative).read_bytes() for relative in contents}
                reconcile(local, checked, {**metadata, 'last_run':status})
        except Exception as error:
            status.update(local='失败', errors=1, error=type(error).__name__+': '+str(error))
            # Report locally when possible; never replace the original error with status failure.
            try:
                write_status(local, status)
            except Exception:
                pass
            atomic(state_dir/'last-run.json',json.dumps(status,ensure_ascii=False).encode())
            return status
        if config.get('icloud_vault') and not local_only:
            try:
                # Send the same validated path snapshot, not a second default configuration.
                process = subprocess.run([sys.executable, '-B', str(REPO/'scripts/obsidian.py'), '_cloud-step'],
                                         input=json.dumps(config),capture_output=True,text=True,timeout=45)
                if process.returncode:
                    atomic(state_dir/'cloud-error.log',process.stderr.encode())
                    raise RuntimeError('Cloud copying failed; inspect cloud-error.log in the external state directory.')
                status = managed(local)['last_run']
            except Exception as error:
                status.update(cloud='失败',errors=1,error=type(error).__name__+': '+str(error))
                write_status(local,status)
        atomic(state_dir/'last-run.json',json.dumps(status,ensure_ascii=False).encode())
        return status
