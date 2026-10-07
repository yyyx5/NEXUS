"""Deterministic human reading projection of existing Nexus facts; no inference."""
import datetime, decimal, hashlib, json, pathlib, re, sqlite3
from zoneinfo import ZoneInfo
TZ=datetime.timezone.utc
WORDS={'active':'有效','review':'待整理','pending':'待处理','unclassified':'未分类','uncategorized':'未分类','unknown':'未明确','life':'生活','生活':'生活','work':'工作','health':'健康','旅行':'旅行','travel':'旅行','open':'待完成','done':'已完成','cancelled':'已取消','paused':'已暂停','planned':'计划中','occurred':'已发生','closed':'已结束','linked':'已关联','booked':'已入账','quote':'报价','budget':'预算','commitment':'待付款承诺','expense':'支出','income':'收入','refund':'退款','paid':'已支付','unpaid':'未支付','partial':'部分支付','user_report':'本人记录','third_party_report':'第三方说法','user_judgment':'本人判断','user_feeling':'本人感受','ai_inference':'AI推论（非事实）','unconfirmed':'待确认','plan':'计划','stated':'明确表述','uncertain':'不确定','retracted':'已撤回','supports':'依据','corrects':'纠正依据','context':'背景','contradicts':'不同说法','private':'私人','restricted':'受限'}
def word(v):return WORDS.get(str(v),str(v))
def date(v,precision=None,record=False):
    if not v:return '未明确'
    try:
        dt=datetime.datetime.fromisoformat(str(v).replace('Z','+00:00'))
        if record or precision=='instant':
            if dt.tzinfo:dt=dt.astimezone(TZ)
            return dt.strftime('%Y年%m月%d日 %H:%M')
        if precision=='year':return dt.strftime('%Y年')
        if precision=='month':return dt.strftime('%Y年%m月')
        return dt.strftime('%Y年%m月%d日')
    except ValueError:return str(v)
def event_time(r):
    if r['valid_from'] and r['time_precision']!='unknown':
        text=date(r['valid_from'],r['time_precision'])
        if r['valid_to']:text+=' — '+date(r['valid_to'],r['time_precision'])
        return text, r['valid_from'][:10] if r['time_precision'] in ('day','instant','range') else '', 'Nexus时间字段'
    # Only an unambiguous full calendar date explicitly present in the text.
    raw=r['body']
    matches=list(re.finditer(r'(20\d{2})(?:年|[-/])(\d{1,2})(?:月|[-/])(\d{1,2})(?:日)?',raw))
    valid=[]
    for m in matches:
        try:valid.append((m,datetime.date(*map(int,m.groups()))))
        except ValueError:pass
    days={d for m,d in valid}
    if len(days)==1:
        m,d=valid[0];end=re.match(r'\s*(?:至|到|—|~|～)\s*(?:(20\d{2})[-/年])?(\d{1,2})[-/月](\d{1,2})(?:日)?',raw[m.end():])
        text=date(d.isoformat());prefix=d.isoformat()
        if end:
            try:
                e=datetime.date(int(end.group(1) or d.year),int(end.group(2)),int(end.group(3)))
                if e>=d:text+=' — '+date(e.isoformat())
            except ValueError:pass
        return text,prefix,'原文明确日期（仅镜像展示）'
    return '未明确','','未推测'
def clean(v):
    s=re.sub(r'[\\/:*?"<>|\[\]#^\x00-\x1f]',' ',str(v));s=re.sub(r'\s+',' ',s).strip(' .')
    return s[:90] or '无标题记录'
def esc(v):return str(v).replace('|','／').replace('\n',' ').replace('[','（').replace(']','）')
def link(path,title):return '[['+path[:-3]+'|'+esc(title)+']]'
def money(minor,scale,currency):
    n=decimal.Decimal(minor).scaleb(-scale)
    unit={'CNY':'元','USD':'美元','EUR':'欧元','JPY':'日元'}.get(currency,currency)
    value=format(n,'f').rstrip('0').rstrip('.') if scale and '.' in format(n,'f') else format(n,'f')
    return value+' '+unit

def export(config, folders, classify, page):
    global TZ
    TZ=ZoneInfo(config.get('timezone','UTC'))
    db=sqlite3.connect(pathlib.Path(config['database']).as_uri()+'?mode=ro',uri=True,timeout=10);db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
    if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('SQLite quick_check failed')
    total=db.execute('SELECT count(*) FROM item').fetchone()[0]
    rows=db.execute('SELECT i.kind,i.created_at AS recorded_at,r.* FROM item i JOIN revision r ON i.head_revision_id=r.revision_id ORDER BY i.created_at,i.item_id').fetchall()
    if len(rows)!=total:raise ValueError('missing item head')
    data={};paths={};used=set();explicit_trips=set()
    def eligible(row):
        payload=json.loads(row['payload_json'])
        if row['status'] in ('deleted','merged','invalid','superseded') or row['certainty']=='retracted':return False
        if payload.get('status') in ('merged','invalid','superseded','deleted') or payload.get('merged_into'):return False
        sensitive=row['visibility']=='restricted' or row['domain'].lower() in ('health','健康')
        return config.get('include_sensitive',False) or not sensitive
    included={r['item_id'] for r in rows if eligible(r)}
    group_defs={r['item_id']:(r,json.loads(r['payload_json'])['nexus_group']) for r in rows if r['item_id'] in included and r['status']=='active' and isinstance(json.loads(r['payload_json']).get('nexus_group'),dict)}
    memberships={}
    for a in db.execute("SELECT r.item_id,a.object_item_id FROM item i JOIN revision r ON i.head_revision_id=r.revision_id JOIN relation a ON a.revision_id=r.revision_id WHERE a.predicate='for_group' AND r.status='active'"):
        if a['object_item_id'] in group_defs:memberships.setdefault(a['item_id'],set()).add(a['object_item_id'])
    group_dirs={};used_dirs=set()

    for row in rows:
        payload=json.loads(row['payload_json'])
        if payload.get('trip_item_id'):explicit_trips.add(payload['trip_item_id'])
        explicit_trips.update(str(t)[5:] for t in json.loads(row['tags_json']) if str(t).startswith('trip:itm_'))
    for gid,(row,g) in group_defs.items():
        gp=json.loads(row['payload_json']);root=classify(row,gp,None)
        if root=='03-生活' and gid in explicit_trips:root='02-旅行'
        name=clean(g.get('name') or row['title']);directory=root+'/'+name
        if directory.casefold() in used_dirs:directory+='（'+gid[-8:]+'）'
        used_dirs.add(directory.casefold());group_dirs[gid]=directory
    for r in rows:
        p=json.loads(r['payload_json'])
        if r['item_id'] not in included:continue
        item=r['item_id']
        if not re.fullmatch(r'itm_[A-Za-z0-9_-]+',item):raise ValueError('invalid item id')
        fin=db.execute('SELECT * FROM financial_detail WHERE revision_id=?',(r['revision_id'],)).fetchone()
        f=classify(r,p,fin);title=r['title'].strip() or '无标题记录'
        gid=p.get('grouping',{}).get('group_id') if isinstance(p.get('grouping'),dict) else None
        if f=='03-生活' and (item in explicit_trips or gid in explicit_trips):f='02-旅行'
        # Title/date come from actual fields; a missing event date never uses record date.
        _,known_date,_=event_time(r);prefix=(known_date+' · ') if known_date else ''
        filename=clean(title)
        if prefix and not filename.startswith(known_date):filename=prefix+filename
        if filename in ('索引','未分类索引','时间线','同步状态'):filename+='（记录）'
        group_ids=memberships.get(item,set())
        if item in group_dirs:rel=group_dirs[item]+'/00-档案首页.md'
        elif len(group_ids)==1 and f!='09-未分类':rel=group_dirs[next(iter(group_ids))]+'/条目明细/'+filename+'.md'
        else:rel=f+'/'+filename+'.md'
        if rel.casefold() in used:rel=str(pathlib.PurePosixPath(rel).with_name(filename+'（'+item[-8:]+'）.md'))
        if rel.casefold() in used:raise ValueError('duplicate reading filename')
        used.add(rel.casefold());paths[item]=rel;data[item]=(r,p,fin,f,title)
    contents={};items={};buckets={f:[] for f in folders};unc=[];timeline=[]
    groups={item:(p['nexus_group'].get('name') or title) for item,(r,p,fin,f,title) in data.items() if isinstance(p.get('nexus_group'),dict)}
    for item,(r,p,fin,f,title) in data.items():
        rel=paths[item];title=groups.get(item,title);recorded=date(r['recorded_at'],record=True);updated=date(r['created_at'],record=True)
        event,_,time_basis=event_time(r)
        tags=[t for t in json.loads(r['tags_json']) if not re.match(r'(trip:)?itm_|rev_|src_',str(t))]
        status='待整理' if f=='09-未分类' else word(r['status'])
        body=f'> **{f[3:]}** · {status}\n> 事件时间：{event}　｜　记录时间：{recorded}\n\n'
        raw=r['body'].strip();first=raw.splitlines()[0] if raw else ''
        if first.lstrip('# ').strip()==title and first.startswith('#'):raw='\n'.join(raw.splitlines()[1:]).lstrip()
        if p.get('aggregate_kind')=='snapshot':body+='> [!note] 原有汇总是历史快照，不代表实时合计。完整明细见下方档案入口。\n\n'
        body+=raw+'\n'
        attrs=[]
        if fin:
            attrs += [('金额',money(fin['amount_minor'],fin['scale'],fin['currency'])),('收支',word(fin['direction'])),('账目状态',word(fin['entry_class']))]
        task=db.execute('SELECT * FROM task_detail WHERE revision_id=?',(r['revision_id'],)).fetchone()
        schedule=db.execute('SELECT * FROM schedule_detail WHERE revision_id=?',(r['revision_id'],)).fetchone()
        if task:
            attrs.append(('待办状态',word(task['state'])))
            if task['due_date']:attrs.append(('截止时间',date(task['due_date'])))
            elif task['due_expression']:attrs.append(('截止表述',task['due_expression']))
        if schedule:
            attrs.append(('日程状态',word(p.get('schedule_state') or r['temporal_status'])))
            if schedule['start_date']:attrs.append(('开始时间',date(schedule['start_date'])))
            if schedule['end_date']:attrs.append(('结束时间',date(schedule['end_date'])))
        labels={'category':'类别','nights':'住宿晚数','payment_status':'付款状态','payment_method':'付款方式','funding_source':'付款来源'}
        for key,label in labels.items():
            if p.get(key) is not None:attrs.append((label,('待付款' if p[key]=='pending' else word(p[key])) if key=='payment_status' else word(p[key])))
        group_ids={x[0] for x in db.execute("SELECT object_item_id FROM relation WHERE revision_id=? AND predicate='for_group'",(r['revision_id'],))}
        if isinstance(p.get('grouping'),dict) and p['grouping'].get('group_id'):group_ids.add(p['grouping']['group_id'])
        if p.get('trip_item_id'):group_ids.add(p['trip_item_id'])
        for gid in sorted(group_ids):
            if gid in paths:attrs.append(('所属档案',link(paths[gid],groups.get(gid,data[gid][4]))))
        if isinstance(p.get('nexus_group'),dict):
            g=p['nexus_group'];attrs.append(('档案状态',word(g.get('state','unknown'))))
            if g.get('start_date'):attrs.append(('档案开始',date(g['start_date'])))
            if g.get('end_date'):attrs.append(('档案结束',date(g['end_date'])))
            members=[link(paths[x],data[x][4]) for x in data if x!=item and item in memberships.get(x,set())]
            if members:
                full=group_dirs[item]+'/01-完整档案.md'
                body+='\n## 阅读本档案\n\n'+link(full,'连续阅读完整档案')+'\n\n共 **'+str(len(members))+'** 条正式关联明细。财务、行程和其他记忆均在此档案文件夹下。\n\n## 条目明细\n\n'+'\n'.join('- '+x for x in members)+'\n'
        if tags:attrs.append(('标签','、'.join(map(str,tags))))
        if attrs:body+='\n## 要点\n\n'+'\n'.join('- **'+label+'**：'+str(value) for label,value in attrs)+'\n'
        if r['assertion_kind']!='user_report' or r['certainty']!='stated':body+='\n> '+word(r['assertion_kind'])+' · '+word(r['certainty'])+'。保留原始表述，不视为已证实结论。\n'
        evidence=db.execute('SELECT e.*,s.namespace,s.channel FROM evidence e JOIN source s USING(source_id) WHERE revision_id=? ORDER BY e.source_id,e.start_char',(r['revision_id'],)).fetchall()
        if evidence:
            body+='\n> [!quote]- 原始依据（点击展开）\n'
            for e in evidence:
                body+='>\n> **'+word(e['role'])+'**\n'+''.join('> '+line+'\n' for line in e['quote'].splitlines())
        body+='\n> [!info]- Nexus 追溯信息（点击展开）\n> - 时间依据：'+time_basis+'\n> - 记录编号：'+item+'\n> - 修订：第 '+str(r['version'])+' 版\n> - 修订编号：'+r['revision_id']+'\n> - 最近更新：'+updated+'\n'
        for e in evidence:body+='> - 来源编号：'+e['source_id']+'（字符 '+str(e['start_char'])+'–'+str(e['end_char'])+'）\n'
        body+='\n*由 Nexus 单向生成。归档和纠错请回到 Nexus 或其接入的助手中处理。*\n'
        fields={'nexus_item_id':item,'revision':r['version'],'source':'nexus','updated':r['created_at'],'标题':title,'分类':f[3:],'状态':status,'事件时间':event,'记录时间':recorded}
        contents[rel]=page(title,body,fields)
        items[item]={'revision':r['version'],'updated':r['created_at'],'path':rel,'render_sha256':hashlib.sha256(contents[rel]).hexdigest()}
        entry=(rel,title,event,recorded,status,item);buckets[rel.split('/')[0]].append(entry);timeline.append(entry)
        if f=='09-未分类':unc.append(entry)
    for gid,directory in group_dirs.items():
        if gid not in data:continue
        members=[x for x in data if x!=gid and gid in memberships.get(x,set())]
        if not members:continue
        title=groups[gid];parts=[]
        for member in members:
            row,payload,fin,_,member_title=data[member]
            # Reuse the readable note; provenance remains in its linked detail page.
            text=contents[paths[member]].decode().split('---\n',2)[2]
            text=text.split('> [!quote]-',1)[0].split('> [!info]-',1)[0]
            text=re.sub(r'^# .+\n','',text.lstrip(),count=1)
            text=re.sub(r'^(#{1,5}) ',r'\1# ',text,flags=re.M)
            parts.append('## '+member_title+'\n\n'+link(paths[member],'打开明细与原始依据')+'\n\n'+text.strip())
        contents[directory+'/01-完整档案.md']=page(title+' · 完整档案','本页按 Nexus 正式档案关联汇集 **'+str(len(members))+'** 条明细，按记录时间排列。各条原文、事件日期与明细依据保留；不会合并或修改 Nexus 条目。\n\n'+link(paths[gid],'返回档案首页')+'\n\n'+'\n\n---\n\n'.join(parts),{'nexus_group_id':gid,'档案':title,'明细数量':len(members)})
    pending=db.execute("SELECT intent_id,args_json,status,created_at FROM pending_intent WHERE status NOT IN ('completed','cancelled') ORDER BY created_at").fetchall() if config.get('include_sensitive',False) else []
    for r in pending:
        pid=r['intent_id']
        if not re.fullmatch('[A-Za-z0-9_-]+',pid):raise ValueError('invalid intent id')
        a=json.loads(r['args_json']);payload=a.get('item',a)
        if not isinstance(payload,dict):payload={}
        title=payload.get('title') or '待处理记录';body=payload.get('body') or '内容尚待 Nexus 完成写入，请在 Nexus 中查看待处理项。'
        recorded=date(datetime.datetime.fromtimestamp(r['created_at'],TZ).isoformat(),record=True)
        rel='09-未分类/'+clean(title)+'（待处理-'+pid[-8:]+'）.md'
        contents[rel]=page(title,'记录时间：'+recorded+'\n\n'+body+'\n\n> [!info]- 追溯信息\n> 尚未生成 item_id；待处理编号：'+pid,{'状态':word(r['status'])})
        unc.append((rel,title,'未明确',recorded,word(r['status']),'尚未生成；intent '+pid))
    db.rollback();db.close()
    def listing(entries,unclassified=False):
        if unclassified:
            head='| 记录时间 | 标题 / 摘要 | 当前状态 | Nexus item_id |\n|---|---|---|---|\n'
            return head+'\n'.join('| '+rec+' | '+link(path,title).replace('|','\\|')+' | '+state+' | '+iid+' |' for path,title,event,rec,state,iid in entries)+'\n'
        return '\n'.join('- '+link(path,title)+'\n  - '+('事件：'+event if event!='未明确' else '事件时间未明确')+' · 记录：'+rec+' · '+state for path,title,event,rec,state,iid in entries)+'\n'
    contents['09-未分类/未分类索引.md']=page('未分类索引',f'**待整理：{len(unc)} 条**\n\n这里展示分类不明确或仍待整理的记忆。请在 Nexus 中指定记录编号继续归档；本页面不会回写 Nexus。\n\n'+listing(unc,True))
    contents['01-时间线/时间线.md']=page('时间线','按实际记录时间从新到旧排列；每条单独标明已知事件时间。\n\n'+listing(list(reversed(timeline))))
    for f,entries in buckets.items():
        if f in ('01-时间线','09-未分类','99-系统'):continue
        overview=[entry for entry in entries if entry[5] in group_dirs or '/条目明细/' not in entry[0]]
        archive_count=sum(entry[5] in group_dirs for entry in overview)
        contents[f+'/索引.md']=page(f[3:],f'共 **{archive_count}** 个档案、**{len(overview)-archive_count}** 条独立记录；含档案明细共 **{len(entries)}** 条 Nexus 记录。\n\n'+(listing(list(reversed(overview))) if overview else '暂无可靠归入此分类的记录。\n'))
    contents['00-首页.md']=page('Nexus',f'## 待整理\n\n**未分类记录：{len(unc)} 条**\n\n[[09-未分类/未分类索引|打开待整理清单]]\n\n## 浏览记忆\n\n[[01-时间线/时间线|按时间浏览]]\n\n'+'\n'.join('- [['+f+'/索引|'+f[3:]+']] · '+str(sum(e[5] in group_dirs for e in buckets[f]))+' 个档案 · '+str(sum(e[5] not in group_dirs and '/条目明细/' not in e[0] for e in buckets[f]))+' 条独立记录' for f in folders[1:8])+f'\n\n当前可读记录 **{len(items)}** 条。\n\n## 同步\n\n[[99-系统/同步状态|查看同步状态]]\n\nNexus 是唯一事实源。本地为可读镜像与网络缓冲；iCloud 为阅读副本。此处改动不会回写。')
    return contents,{'items':items,'total':total,'unclassified':len(unc),'pending':len(pending),'render_version':3,'include_sensitive':config.get('include_sensitive',False),'archives':{gid:{'name':groups[gid],'directory':directory,'members':[x for x in data if x!=gid and gid in memberships.get(x,set())]} for gid,directory in group_dirs.items() if gid in data}}
