"""New fictional Obsidian example; never reads a configured personal database."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'examples'))
from fixture import Fixture, run_demo
from extensions.obsidian.mirror import outside_repo, run

def demonstrate(root):
    fixture = Fixture(root/'fictional-source')
    try:
        run_demo(fixture)
        text = '这是一条完全虚构、尚待整理的想法。'
        fixture.call('nexus_save',{'proposals':[{'domain':'unclassified','title':'虚构待整理想法','body':text}]},text)
        config = {'enabled':True,'database':str(root/'fictional-source/data/nexus.sqlite3'),
                  'local_vault':str(root/'Nexus'),'icloud_vault':None,'include_sensitive':False,'timezone':'UTC'}
        result = run(config,root/'state')
        print(json.dumps({'fictional':True,'vault':str(root/'Nexus'),**result},ensure_ascii=False,indent=2))
        return 1 if result.get('errors') else 0
    finally:
        fixture.close()

def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='Fictional demo; no personal memory or iCloud access.')
    parser.add_argument('--output',help='Optional new directory outside the repository; retained for reading.')
    args = parser.parse_args()
    if args.output:
        root = outside_repo(args.output)
        if root.exists():
            parser.error('Use a new directory so an existing mirror cannot be replaced.')
        root.mkdir(parents=True)
        return demonstrate(root)
    with tempfile.TemporaryDirectory(prefix='nexus-obsidian-fictional-') as temporary:
        result = demonstrate(Path(temporary))
        print('Temporary fictional demo removed; use --output with a new external directory to keep it.')
        return result
if __name__ == '__main__':
    raise SystemExit(main())
