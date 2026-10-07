"""Audit files, staged blobs and reachable history. Never print matched content.
Optional --deny-file supplies private literal identifiers from outside the repo.
"""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'home-path': re.compile('/' + r'(?:Users|home)/[^/\s]+'),
    'phone': re.compile(r'(?<![0-9])1[3-9][0-9]{9}(?![0-9])'),
    'bank-number': re.compile(r'(?<![A-Za-z0-9])[0-9]{16,19}(?![A-Za-z0-9])'),
    'email': re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
    'credential': re.compile(r'(?:gh' + r'[opusr]_[A-Za-z0-9]{20,}|sk' + r'-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)'),
    'secret-assignment': re.compile(r'''(?i)(?:api[_-]?key|token|password|secret)\s*[=:]\s*["'][A-Za-z0-9_+/=-]{20,}["']'''),
}
PUBLIC_EMAIL = re.compile(r'^(?:[0-9]+\+[^@]+@users\.noreply\.github\.com|noreply@github\.com)$')
BAD_SUFFIX = re.compile(r'(?i)(?:\.sqlite[^/]*|\.db(?:-.*)?|\.log|\.jsonl|\.zst|\.png|\.jpe?g|\.pdf|\.xlsx|\.zip|\.pem|\.key|\.p12|-wal|-shm)$')
BAD_DIRS = {'data','state','archive','backups','logs','attachments','conversations','runtime','sandbox'}

def git(*args):
    if not (ROOT / '.git').is_dir():
        raise subprocess.CalledProcessError(1, ['git'])
    return subprocess.check_output(['git', '-C', str(ROOT), *args], stderr=subprocess.DEVNULL)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deny-file', type=Path)
    args = parser.parse_args()
    deny = [x.strip() for x in args.deny_file.read_text().splitlines() if x.strip()] if args.deny_file else []
    findings = set()
    checked = 0
    def inspect(label, name, blob):
        nonlocal checked
        checked += 1
        parts = Path(name).parts
        if BAD_SUFFIX.search(name) or set(parts[:-1]) & BAD_DIRS or (Path(name).name.startswith('.env') and Path(name).name != '.env.example') or Path(name).name == 'settings.json':
            findings.add((label, 'prohibited-file'))
        if b'\x00' in blob: findings.add((label,'binary-content'))
        try: text = blob.decode('utf-8')
        except UnicodeDecodeError:
            findings.add((label,'non-text-content')); return
        for rule, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                if rule == 'email' and PUBLIC_EMAIL.fullmatch(match.group()): continue
                findings.add((label,rule))
        if any(value.casefold() in text.casefold() for value in deny): findings.add((label,'private-denylist'))
    for path in sorted(ROOT.rglob('*')):
        if set(path.relative_to(ROOT).parts) & {'.git','__pycache__','.venv','node_modules'}: continue
        if path.is_symlink(): findings.add((str(path.relative_to(ROOT)),'symlink')); continue
        if path.is_file(): inspect('file:'+str(path.relative_to(ROOT)),str(path.relative_to(ROOT)),path.read_bytes())
    commits = []
    try:
        staged = git('ls-files','--stage','-z')
    except subprocess.CalledProcessError:
        staged = b''
    for entry in staged.split(b'\x00'):
        if not entry: continue
        meta, name = entry.decode().split('\t',1); mode, oid, stage = meta.split()
        if mode != '100644': findings.add(('index:'+name,'non-regular-mode'))
        inspect('index:'+name,name,git('cat-file','blob',oid))
    try: commits = git('rev-list','--all').decode().splitlines()
    except subprocess.CalledProcessError: pass
    seen = set()
    for commit in commits:
        inspect('commit:'+commit[:12],'metadata',git('show','-s','--format=fuller',commit))
        for entry in git('ls-tree','-r','-z',commit).split(b'\x00'):
            if not entry: continue
            meta, name = entry.decode().split('\t',1); mode, kind, oid = meta.split()
            if kind != 'blob' or mode != '100644': findings.add(('history:'+name,'non-regular-mode')); continue
            if (name,oid) in seen: continue
            seen.add((name,oid)); inspect('history:'+name,name,git('cat-file','blob',oid))
    try:
        for tag in git('tag').decode().splitlines():
            if git('cat-file','-t','refs/tags/'+tag).strip()==b'tag':
                inspect('tag:'+tag,'metadata',git('cat-file','tag','refs/tags/'+tag))
    except subprocess.CalledProcessError: pass
    for label, rule in sorted(findings): print(label+' :: '+rule)
    print(f'Checked {checked} text entries; {len(commits)} reachable commits; findings={len(findings)}')
    raise SystemExit(1 if findings else 0)

if __name__ == '__main__': main()
