"""Opt-in setup and reversible pause; no change to Nexus core deployment."""
import json
from pathlib import Path
import plistlib
import subprocess
import sys
from .mirror import REPO, atomic, outside_repo, validate

NOTICE_ZH = '''
可选功能：Nexus 人生记录器的 Obsidian 阅读镜像（实验版）

你可以只使用 Nexus 保存、查询和整理人生记忆；不部署此扩展也完整可用。
启用后：Nexus → 本地 Nexus Markdown → 可选 iCloud Nexus。
可以按中文标题、时间线、正式档案浏览记忆，看到待整理清单与来源依据。
同一档案在同一个文件夹，并有连续阅读的完整页；不靠 AI 猜档案归属。

请在选择前了解：
- Nexus 始终是唯一事实源。没有 Obsidian → Nexus 的反向同步。
- 镜像是未加密的阅读副本；自动生成笔记的编辑会被后续同步覆盖。
- 默认不导出健康/受限记录和未完成写入；包含它们需要单独选择。
- 默认仅本地；选择 iCloud 会把所选记忆交给 Apple iCloud 同步。
- 只清理清单内带生成标记的文件，保留 .obsidian 和其他用户文件。
- 不安装 Obsidian、插件或模型；同步不调用 AI，基础同步 0 Token。
- 中文阅读模板；Python 3.10+，当前支持 macOS/Linux，Windows 未支持。
- macOS 后台访问 iCloud 可能需要系统权限；写入成功不等于手机已下载。

现在跳过没有损失；以后随时重新运行同一个 setup 命令即可启用。
也可让你选择的 AI 助手根据公开说明辅助部署；AI 不属于镜像核心代码。
'''
NOTICE_EN = '''
Optional: Obsidian reading mirror for the Nexus life recorder (experimental)

Nexus works fully on its own. This extension is optional and disabled by default.
Enable it to create Nexus → local Markdown Nexus → optional iCloud Nexus.
Browse readable titles, timelines, existing dossiers, unclassified records and evidence.
Each dossier gets one folder and a continuous reading page; no AI guesses membership.

Before choosing:
- Nexus remains the sole source of truth. No Obsidian → Nexus writes.
- Mirrors are unencrypted copies. Edits to generated notes are overwritten on sync.
- Health/restricted records and unfinished intents are excluded unless separately enabled.
- Local-only is the default. iCloud sends the selected memories to Apple's sync service.
- Cleanup is limited to marked, manifest-owned files; .obsidian and user files are kept.
- No Obsidian, plugin or model is installed. Deterministic sync uses zero model tokens.
- Reading templates are Chinese; Python 3.10+, macOS/Linux; Windows is unsupported.
- macOS background iCloud access may need permission; local writes do not prove mobile delivery.

Skip now and rerun this same setup command whenever you change your mind.
An AI assistant may help follow the public instructions; AI is outside the mirror core.
'''

def default_settings():
    return Path.home()/'.config/nexus/obsidian/settings.json'

def settings_path(path=None):
    return outside_repo(path or default_settings())

def load(path):
    path = settings_path(path)
    if not path.exists():
        return {'enabled': False}
    return json.loads(path.read_text(encoding='utf-8'))

def yes(prompt, input_fn=input):
    try:
        return input_fn(prompt).strip().lower() in ('y','yes','是')
    except EOFError:
        return False

def detected_icloud():
    # Only use an actually existing Obsidian iCloud Documents container.
    mobile = Path.home()/'Library/Mobile Documents'
    if not mobile.is_dir():
        return None
    candidates = [path/'Documents' for path in mobile.iterdir()
                  if path.name == 'iCloud~md~obsidian' and (path/'Documents').is_dir()]
    return candidates[0]/'Nexus' if len(candidates) == 1 else None

def setup(args, input_fn=input, output=print):
    english = args.language == 'en'
    output(NOTICE_EN if english else NOTICE_ZH)
    path = settings_path(args.config)
    if args.skip or not (args.enable or yes('Enable optional reading mirror? [y/N]: ' if english else '现在启用可视阅读镜像？[y/N，默认跳过]：',input_fn)):
        output('Skipped; nothing changed. Rerun setup later; disable pauses an existing mirror.' if english else '已跳过，本次未改任何配置。日后重跑 setup 即可；已有镜像可用 disable 暂停。')
        return {'enabled':False,'changed':False}
    old = load(path)
    def ask(value, previous, default, question):
        if value is not None:
            return value
        candidate = previous or default
        if args.enable:
            return candidate
        try:
            answer = input_fn(question+(' ['+str(candidate)+']' if candidate else '')+': ').strip()
        except EOFError:
            answer = ''
        return answer or candidate
    database = ask(args.database,old.get('database'),None,'Nexus SQLite database (required)' if english else 'Nexus SQLite 数据库路径（必填）')
    if not database:
        raise ValueError('A Nexus database path is required; no settings changed.')
    local = ask(args.local_vault,old.get('local_vault'),str(Path.home()/'Nexus'),'Local Nexus folder' if english else '本地 Nexus 文件夹')
    timezone = ask(args.timezone,old.get('timezone'),'UTC','Display timezone' if english else '显示时区，例如 Asia/Shanghai')
    sensitive = args.include_sensitive or (not args.enable and yes('Include health/restricted records and unfinished intents? [y/N]: ' if english else '是否包含健康/受限记忆及未完成写入？[y/N]：',input_fn))
    cloud = args.icloud_vault
    if cloud is None and not args.enable and yes('Enable iCloud copy of the selected plaintext memories? [y/N]: ' if english else '是否让 Apple iCloud 同步上述未加密记忆？[y/N]：',input_fn):
        discovered = detected_icloud()
        if not discovered:
            output('No existing Obsidian iCloud container detected; supply your verified path.' if english else '未检测到现有 Obsidian iCloud 容器，请填写自己已确认的路径。')
        cloud = ask(None,old.get('icloud_vault'),str(discovered) if discovered else None,'iCloud Nexus folder' if english else 'iCloud Nexus 文件夹')
        if not cloud:
            raise ValueError('iCloud was selected but no verified path was supplied; no settings changed.')
    config = validate({'enabled':True,'database':database,'local_vault':local,'icloud_vault':cloud,
                       'include_sensitive':bool(sensitive),'timezone':timezone})
    if path.exists():
        atomic(path.with_name('settings.previous.json'),path.read_bytes())
    atomic(path,json.dumps(config,ensure_ascii=False,indent=2).encode())
    output('Configuration saved outside the repository. No database or mirror was changed by setup.' if english else '配置已保存到仓库之外；setup 没有改数据库或生成镜像。')
    output(str(path))
    output('Next: python3 -B scripts/obsidian.py sync --config <your-settings-path>')
    output('Pause: python3 -B scripts/obsidian.py disable --config <your-settings-path>')
    return config

def disable(path):
    path = settings_path(path)
    config = load(path)
    if path.exists():
        config['enabled'] = False
        atomic(path,json.dumps(config,ensure_ascii=False,indent=2).encode())
    return {'enabled':False,'preserved':'Nexus database, mirror notes and existing schedule; scheduled runs now skip.',
            'enable_later':'Rerun setup.'}

def schedule(path, load_now=False, plist_path=None):
    if sys.platform != 'darwin':
        raise ValueError('The launchd helper is macOS-only; other schedulers can invoke sync.')
    path = settings_path(path)
    validate(load(path))
    destination = Path(plist_path) if plist_path else Path.home()/'Library/LaunchAgents/org.nexus.obsidian-mirror.plist'
    label = 'org.nexus.obsidian-mirror'
    state = path.parent/'state'
    state.mkdir(parents=True,exist_ok=True)
    obj = {'Label':label,'ProgramArguments':[sys.executable,'-B',str(REPO/'scripts/obsidian.py'),'sync','--config',str(path)],
           'WorkingDirectory':str(REPO),'StartCalendarInterval':{'Hour':4,'Minute':0},'Umask':63,
           'StandardOutPath':str(state/'launchd.log'),'StandardErrorPath':str(state/'launchd-error.log')}
    # Preserve any existing job rather than replacing its schedule or arguments.
    if destination.exists() and plistlib.loads(destination.read_bytes()) != obj:
        raise ValueError('An existing launchd file differs; review it manually before replacing it.')
    atomic(destination,plistlib.dumps(obj))
    subprocess.run(['/usr/bin/plutil','-lint',str(destination)],check=True)
    if load_now:
        subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(__import__('os').getuid()),str(destination)],check=True)
    return {'plist':str(destination),'loaded':load_now,'schedule':'04:00 in the macOS system timezone',
            'note':'Verify a background run; iCloud may require macOS privacy permission.'}
