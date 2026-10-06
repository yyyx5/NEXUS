"""Nexus versioned source-evidenced revision storage."""
from pathlib import Path
import datetime as dt
from decimal import Decimal
import hashlib
import json
import os
import sqlite3
import uuid

BASE = Path(__file__).resolve().parent
SANDBOX = BASE / 'sandbox'
IMMUTABLE = ('revision','evidence','relation','entity_alias','operation','task_detail','financial_detail','schedule_detail')


def canon(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Conflict(ValueError): pass


class Nexus:
    def __init__(self, path):
        path=Path(path).resolve()
        os.umask(0o077);path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=3,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('pragma foreign_keys=on')
        self.db.execute('pragma synchronous=full')
        if not self.db.execute("select 1 from sqlite_master where name='source'").fetchone():
            self.db.executescript((BASE.parent/'schema'/'schema.sql').read_text())
            for table in IMMUTABLE:
                for action in ('update','delete'):
                    self.db.execute(f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable {table}'); END")
            self.db.executescript("""CREATE TRIGGER validate_quote BEFORE INSERT ON evidence
            WHEN NEW.quote != substr((SELECT raw_text FROM source WHERE source_id=NEW.source_id),NEW.start_char+1,NEW.end_char-NEW.start_char)
            BEGIN SELECT RAISE(ABORT,'evidence span mismatch'); END;""")
            self.db.execute('pragma user_version=1')
        elif self.db.execute('pragma user_version').fetchone()[0]!=1:
            raise ValueError('unsupported schema version')
        os.chmod(path,0o600)

    def close(self):self.db.close()

    def head(self,item_id):
        row=self.db.execute('SELECT r.*,i.kind FROM item i JOIN revision r ON i.head_revision_id=r.revision_id WHERE i.item_id=?',(item_id,)).fetchone()
        if not row:raise ValueError('unknown item')
        return dict(row)

    def evidence(self,sid,quote=None,role='supports'):
        row=self.db.execute('SELECT raw_text FROM source WHERE source_id=?',(sid,)).fetchone()
        if not row:raise ValueError('unknown source')
        raw=row['raw_text'];quote=raw if quote is None else quote
        start=raw.find(quote)
        if not quote or start<0:raise ValueError('quote not in source')
        return {'source_id':sid,'role':role,'quote':quote,'start_char':start,'end_char':start+len(quote)}

    def insert_revision(self,proposal,evidence,*,item_id=None,expected_revision=None,action='create',actor='nexus'):
        if not evidence or len(evidence)>8:raise ValueError('each revision needs 1..8 evidence links')
        for ev in evidence:
            row=self.db.execute('SELECT raw_text FROM source WHERE source_id=?',(ev['source_id'],)).fetchone()
            if not row or row['raw_text'][ev['start_char']:ev['end_char']]!=ev['quote'] or not ev['quote']:
                raise ValueError('unverifiable evidence')
        p=dict(proposal);kind=p.get('kind','record')
        assertion=p.get('assertion_kind','user_report');certainty=p.get('certainty','stated')
        perspective=p.get('perspective','user');status=p.get('status','active')
        if assertion=='ai_inference' and (certainty not in ('uncertain','unknown') or perspective!='ai' or status!='review'):
            raise ValueError('AI inference cannot be promoted to fact')
        caution=any(any(w in ev['quote'] for w in ('可能','好像','也许','未确认','还没确认')) for ev in evidence if ev['role'] in ('supports','corrects'))
        if caution and certainty=='stated':raise ValueError('explicit uncertainty cannot be discarded')
        if assertion=='third_party_report' and perspective!='third_party':raise ValueError('hearsay attribution required')
        if assertion in ('user_feeling','user_judgment') and perspective!='user':raise ValueError('subjective attribution required')
        if kind=='entity' and any(k in p.get('payload',{}) for k in ('personality','diagnosis','inferred_relationship')):
            raise ValueError('no inferred personality or relationship on entity')
        title=p.get('title','');body=p.get('body','')
        if not isinstance(title,str) or not isinstance(body,str) or len(title)>200 or len(body)>8000:
            raise ValueError('bounded strings required')
        if len(canon(p))>20000:raise ValueError('proposal exceeds local size budget')
        if item_id:
            old=self.head(item_id)
            if not expected_revision or old['revision_id']!=expected_revision:raise Conflict('stale expected_revision')
            if kind!=old['kind']:raise ValueError('item identity kind immutable')
            if action=='create':raise ValueError('update requires explicit action')
            version=old['version']+1;parent=old['revision_id']
        else:
            if action!='create' or expected_revision:raise ValueError('new item requires create')
            item_id='itm_'+uuid.uuid4().hex;version=1;parent=None
            self.db.execute('INSERT INTO item VALUES (?,?,NULL,?)',(item_id,kind,now()))
        rid='rev_'+uuid.uuid4().hex
        temporal=p.get('temporal_status','unknown')
        r={'revision_id':rid,'item_id':item_id,'version':version,'parent_revision_id':parent,
           'action':action,'status':status,'domain':p.get('domain','uncategorized'),'title':title,'body':body,
           'tags_json':canon(p.get('tags',[])),'payload_json':canon(p.get('payload',{})),
           'assertion_kind':assertion,'certainty':certainty,'perspective':perspective,'temporal_status':temporal,
           'valid_from':p.get('valid_from'),'valid_to':p.get('valid_to'),'time_expression':p.get('time_expression'),
           'time_precision':p.get('time_precision','unknown'),'timezone':p.get('timezone','Asia/Shanghai'),
           'visibility':p.get('visibility','private'),'actor':actor,'reason':p.get('reason',action),
           'extraction_json':canon(p.get('extraction',{'method':'host_bound_tool','model':None})),
           'created_at':now()}
        r['revision_sha256']=digest(canon(r))
        columns=list(r)
        self.db.execute('INSERT INTO revision ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',[r[k] for k in columns])
        for ev in evidence:
            self.db.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?)',(rid,ev['source_id'],ev['role'],ev['quote'],ev['start_char'],ev['end_char']))
        for n,edge in enumerate(p.get('relations',[])):
            self.db.execute('INSERT INTO relation VALUES (?,?,?,?,?,?)',(rid,n,edge.get('subject_item_id',item_id),edge['predicate'],edge['object_item_id'],canon(edge.get('qualifiers',{}))))
        if p.get('aliases') and kind!='entity':raise ValueError('aliases only belong to entity')
        for alias in p.get('aliases',[]):
            self.db.execute('INSERT INTO entity_alias VALUES (?,?,?)',(rid,item_id,alias))
        self._details(rid,p)
        self.db.execute('UPDATE item SET head_revision_id=? WHERE item_id=?',(rid,item_id))
        self.db.execute('DELETE FROM current_fts WHERE item_id=?',(item_id,))
        if status=='active':self.db.execute('INSERT INTO current_fts VALUES (?,?,?)',(item_id,title,body))
        result={'item_id':item_id,'revision_id':rid,'version':version,'status':status}
        return result

    def _details(self,rid,p):
        if 'task' in p:
            t=p['task'];self.db.execute('INSERT INTO task_detail VALUES (?,?,?,?,?)',(rid,t['state'],t.get('due_date'),t.get('due_expression'),t.get('timezone','Asia/Shanghai')))
        if 'financial' in p:
            f=p['financial'];amount=f['amount_minor'];scale=f.get('scale',2)
            if p.get('temporal_status')=='planned' and f.get('entry_class','booked')=='booked':raise ValueError('planned price is not booked expense')
            if isinstance(amount,bool) or not isinstance(amount,int):raise ValueError('amount must be integer minor units')
            if not isinstance(scale,int) or isinstance(scale,bool):raise ValueError('integer scale required')
            scales={'CNY':2,'USD':2,'EUR':2,'HKD':2,'GBP':2,'JPY':0}
            if f['currency'] not in scales or scale!=scales[f['currency']]:raise ValueError('currency scale must match registered extension')
            self.db.execute('INSERT INTO financial_detail VALUES (?,?,?,?,?,?,?)',(rid,amount,f['currency'],scale,f['direction'],f.get('entry_class','booked'),f.get('occurred_date')))
        if 'schedule' in p:
            s=p['schedule'];self.db.execute('INSERT INTO schedule_detail VALUES (?,?,?,?,?)',(rid,s.get('start_date'),s.get('end_date'),s['time_expression'],s.get('timezone','Asia/Shanghai')))

    @staticmethod
    def minor_units(text,scale=2):
        if isinstance(text,(float,bool)):raise ValueError('decimal text required')
        d=Decimal(str(text));n=d*(10**scale)
        if not d.is_finite() or n!=n.to_integral_value() or n<0 or n>10**12:raise ValueError('invalid amount or precision')
        return int(n)

    def lookup_alias(self,alias):
        return [dict(r) for r in self.db.execute("SELECT DISTINCT a.entity_item_id,r.title FROM entity_alias a JOIN current_item r ON r.revision_id=a.revision_id WHERE a.alias=? AND r.visibility='private'",(alias,))]

    def search(self,text='',domain=None,start=None,end=None,limit=10,char_budget=4000):
        if limit<1 or limit>20 or char_budget<128 or char_budget>8000:raise ValueError('query budget outside allowed range')
        if len(text)>200:raise ValueError('query too long')
        where=['r.visibility=\'private\''];params=[];join=''
        if text:
            if len(text)>=3:
                join=' JOIN current_fts f ON f.item_id=r.item_id';where.append('current_fts MATCH ?');params.append('"'+text.replace('"','""')+'"')
            else:
                where.append('instr(r.title||r.body,?)>0');params.append(text)
        if domain:where.append('r.domain=?');params.append(domain)
        if start:where.append('r.valid_from>=?');params.append(start)
        if end:where.append('r.valid_from<?');params.append(end)
        sql='SELECT r.* FROM current_item r'+join+' WHERE '+' AND '.join(where)+' ORDER BY r.created_at DESC,r.item_id LIMIT ?'
        # Progress handler also bounds CPU work for short Chinese substring queries.
        self.db.set_progress_handler(lambda:1,2000000)
        try:rows=[dict(r) for r in self.db.execute(sql,params+[limit+1])]
        finally:self.db.set_progress_handler(None,0)
        result=[];used=0;truncated=len(rows)>limit
        for row in rows[:limit]:
            refs=[r[0] for r in self.db.execute('SELECT source_id FROM evidence WHERE revision_id=? LIMIT 6',(row['revision_id'],))]
            hit={k:row[k] for k in ('item_id','revision_id','title','domain','assertion_kind','certainty','perspective','temporal_status')}
            hit['excerpt']=row['body'][:320];hit['source_ids']=refs[:5];hit['more_sources']=len(refs)>5
            cost=len(canon(hit))
            if used+cost>char_budget:truncated=True;break
            result.append(hit);used+=cost
        return {'hits':result,'count':len(result),'serialized_chars':used,'truncated':truncated,'coverage':'matching_current_active_records_only'}

    def query(self,template,*,start=None,end=None,entity_id=None):
        """Only fixed parameterized templates are callable, never arbitrary SQL."""
        if template!='financial_totals' and (start is not None or end is not None):raise ValueError('date filters for this template are design-only; use bounded search')
        if template=='financial_totals':
            where=['r.visibility=\'private\'','f.entry_class=\'booked\''];params=[]
            if start:where.append('f.occurred_date>=?');params.append(start)
            if end:where.append('f.occurred_date<?');params.append(end)
            sql='SELECT f.currency,f.scale,f.direction,SUM(f.amount_minor) AS total_minor,COUNT(*) AS count FROM current_item r JOIN financial_detail f USING(revision_id) WHERE '+' AND '.join(where)+' GROUP BY f.currency,f.scale,f.direction'
        elif template=='person_timeline':
            if not entity_id:raise ValueError('explicit disambiguated entity id required')
            sql="SELECT r.item_id,r.kind,r.title,substr(r.body,1,320) AS excerpt,r.assertion_kind,r.certainty,r.perspective,r.temporal_status FROM current_item r WHERE r.visibility='private' AND r.domain NOT IN ('health','健康') AND EXISTS(SELECT 1 FROM relation e WHERE e.revision_id=r.revision_id AND e.object_item_id=?) ORDER BY r.valid_from,r.created_at LIMIT 20";params=[entity_id]
        elif template=='trip_costs':
            if not entity_id:raise ValueError('explicit trip id required')
            sql="SELECT f.currency,f.scale,f.direction,f.entry_class,SUM(f.amount_minor) AS total_minor,COUNT(*) AS count FROM current_item r JOIN financial_detail f USING(revision_id) WHERE r.visibility='private' AND r.domain NOT IN ('health','健康') AND EXISTS(SELECT 1 FROM relation e WHERE e.revision_id=r.revision_id AND e.object_item_id=? AND e.predicate='for_trip') GROUP BY f.currency,f.scale,f.direction,f.entry_class";params=[entity_id]
        elif template=='open_tasks':
            sql="SELECT r.item_id,r.title,t.state,t.due_date FROM current_item r JOIN task_detail t USING(revision_id) WHERE t.state IN ('open','paused') AND r.visibility='private' AND r.domain NOT IN ('health','健康') LIMIT 20";params=[]
        else:raise ValueError('query template not allowed')
        return [dict(r) for r in self.db.execute(sql,params)]

    def delete_preview(self,item_id):
        r=self.head(item_id)
        return {'item_id':item_id,'expected_revision':r['revision_id'],'current_status':r['status'],
                'structural_action':'new_deleted_revision; hidden from current queries','archive_action':'none',
                'source_ids':[x[0] for x in self.db.execute('SELECT source_id FROM evidence WHERE revision_id=?',(r['revision_id'],))]}

    def verify(self):
        errors=[]
        for r in self.db.execute('SELECT * FROM source'):
            if digest(r['raw_text'])!=r['content_sha256']:errors.append('source_hash')
        for row in self.db.execute('SELECT * FROM revision'):
            r=dict(row);h=r.pop('revision_sha256')
            if digest(canon(r))!=h:errors.append('revision_hash')
            if not self.db.execute('SELECT 1 FROM evidence WHERE revision_id=?',(r['revision_id'],)).fetchone():errors.append('missing_evidence')
        for e in self.db.execute('SELECT e.*,s.raw_text FROM evidence e JOIN source s USING(source_id)'):
            if e['raw_text'][e['start_char']:e['end_char']]!=e['quote']:errors.append('span_mismatch')
        errors+=['foreign_key']*len(self.db.execute('pragma foreign_key_check').fetchall())
        if self.db.execute('pragma integrity_check').fetchone()[0]!='ok':errors.append('sqlite_integrity')
        self.db.execute("INSERT INTO current_fts(current_fts) VALUES('integrity-check')")
        expected={(r['item_id'],r['title'],r['body']) for r in self.db.execute('SELECT * FROM current_item')}
        actual={tuple(r) for r in self.db.execute('SELECT * FROM current_fts')}
        if expected!=actual:errors.append('fts_projection')
        return {'errors':errors,'sources':self.db.execute('SELECT count(*) FROM source').fetchone()[0],
                'items':self.db.execute('SELECT count(*) FROM item').fetchone()[0],
                'revisions':self.db.execute('SELECT count(*) FROM revision').fetchone()[0]}

    def rebuild_search(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('DELETE FROM current_fts')
            self.db.execute('INSERT INTO current_fts SELECT item_id,title,body FROM current_item')
            self.db.execute('COMMIT')
        except Exception:self.db.execute('ROLLBACK');raise
