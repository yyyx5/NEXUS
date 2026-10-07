"""Opt-in CLI; no invocation from the Nexus core or its default deployment."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from extensions.obsidian.mirror import cloud_step, run
from extensions.obsidian.setup import disable, load, schedule, settings_path, setup

def main(argv=None):
    os.umask(0o077)
    if argv is None:
        argv = sys.argv[1:]
    # Internal copy worker receives an explicit, validated configuration snapshot.
    if argv == ['_cloud-step']:
        cloud_step(json.load(sys.stdin))
        return 0
    parser = argparse.ArgumentParser(description='Optional Nexus → Obsidian reading mirror. Default: not deployed.')
    commands = parser.add_subparsers(dest='command',required=True)
    choice = commands.add_parser('setup',help='Explain the optional mirror; skip now or enable at any later time.')
    choice.add_argument('--language',choices=('zh','en'),default='zh')
    choice.add_argument('--config')
    flags = choice.add_mutually_exclusive_group()
    flags.add_argument('--enable',action='store_true',help='Explicit noninteractive opt-in; prints deployment notice.')
    flags.add_argument('--skip',action='store_true',help='Leave everything unchanged; setup remains available later.')
    choice.add_argument('--database');choice.add_argument('--local-vault');choice.add_argument('--icloud-vault')
    choice.add_argument('--timezone');choice.add_argument('--include-sensitive',action='store_true')
    sync = commands.add_parser('sync',help='Run an enabled local-first mirror, without model calls.')
    sync.add_argument('--config');sync.add_argument('--local-only',action='store_true')
    pause = commands.add_parser('disable',help='Pause future exports, preserving Nexus and mirror files.')
    pause.add_argument('--config')
    status = commands.add_parser('status',help='Show the saved opt-in choice and last run.')
    status.add_argument('--config')
    timer = commands.add_parser('schedule',help='macOS-only: generate a 04:00 launchd job; loading is separately optional.')
    timer.add_argument('--config');timer.add_argument('--load',action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'setup':
            result = setup(args)
        elif args.command == 'disable':
            result = disable(args.config)
        elif args.command == 'schedule':
            result = schedule(args.config,args.load)
        else:
            path = settings_path(args.config)
            config = load(path)
            if args.command == 'status':
                last = path.parent/'state/last-run.json'
                result = {'enabled':bool(config.get('enabled')),'config_exists':path.exists(),
                          'last_run':json.loads(last.read_text(encoding='utf-8')) if last.exists() else None,
                          'enable_later':'python3 -B scripts/obsidian.py setup'}
            else:
                result = run(config,path.parent/'state',args.local_only)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 1 if result.get('errors') else 0
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
