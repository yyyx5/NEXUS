"""Entirely invented source events and Archive records, generated in isolation.
Not a production importer or an authorization bypass for live channels.
"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nexus'))
from base import canon, digest
from core import Core

class Fixture:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings = {'agent': 'demo-agent', 'account': 'demo-account',
                         'sourceDB': str(self.root / 'transcripts.sqlite3'),
                         'archiveRoot': str(self.root / 'archive'),
                         'owners': {'telegram': ['fictional-owner-tg'], 'wecom': ['fictional-owner-wc']}}
        self.source = sqlite3.connect(self.settings['sourceDB'])
        self.source.executescript('''
        CREATE TABLE session_windows(session_id TEXT PRIMARY KEY,session_key TEXT);
        CREATE TABLE transcript_events(session_id TEXT,seq INTEGER,event_json TEXT,event_zstd BLOB,event_utf8_bytes INTEGER);
        CREATE TABLE conversations(conversation_id TEXT PRIMARY KEY,kind TEXT,account_id TEXT,channel TEXT,
            native_channel_id TEXT,native_direct_user_id TEXT,peer_id TEXT,delivery_target TEXT);
        ''')
        for channel in self.settings['owners']:
            sender = self.settings['owners'][channel][0]
            self.source.execute('INSERT INTO session_windows VALUES(?,?)', (channel, 'agent:demo-agent:'+channel))
            self.source.execute('INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?)',
                                (channel, 'direct', 'demo-account', channel, sender, sender, sender, sender))
        self.source.commit()
        self.sequence = 0
        self.n = Core(self.root / 'data/nexus.sqlite3', self.settings)

    def event(self, text, channel='telegram', preserve=True, tool=None):
        self.sequence += 1
        eid = 'fictional-event-' + str(self.sequence)
        timestamp = '2030-04-12T12:00:00Z'
        sender = self.settings['owners'][channel][0]
        event = {'id': eid, 'timestamp': timestamp, 'message': {'role': 'user', 'content': text,
                 '__openclaw': {'senderId': sender, 'senderIsOwner': True,
                               'transport': {'channel': channel, 'conversationRef': channel}}}}
        self.source.execute('INSERT INTO transcript_events VALUES(?,?,?,NULL,NULL)',
                            (channel, self.sequence, canon(event)))
        ctx = {'agentId': 'demo-agent', 'accountId': 'demo-account', 'sessionId': channel,
               'sessionKey': 'agent:demo-agent:'+channel, 'channel': channel,
               'requesterSenderId': sender, 'senderIsOwner': True, 'conversationRef': channel}
        if tool:
            call = 'fictional-call-' + str(self.sequence)
            assistant = {'id': call, 'parentId': eid, 'timestamp': timestamp,
                         'message': {'role': 'assistant', 'content': [{'type': 'toolCall', 'name': tool, 'id': call}]}}
            self.sequence += 1
            self.source.execute('INSERT INTO transcript_events VALUES(?,?,?,NULL,NULL)',
                                (channel, self.sequence, canon(assistant)))
            ctx['toolCallId'] = call
        else:
            ctx['sourceEventId'] = eid
        self.source.commit()
        b = self.n.binder.native(ctx)
        record = {'schema_version': 1, 'archive_event_id': b['archive_event_id'],
                  'logical_event_id': digest(canon(['demo-agent', channel, eid])),
                  'source_event_id': eid, 'parent_id': None, 'source_event_sha256': b['event_sha256'],
                  'agent_id': 'demo-agent', 'session_id': channel, 'session_key': ctx['sessionKey'],
                  'channel': channel, 'channel_basis': 'fixture', 'conversation_identity': channel,
                  'session_conversations': [], 'platform_message_id': None, 'role': 'user',
                  'event_type': 'message', 'message_type': 'text', 'original_timestamp': timestamp,
                  'original_user_text': text, 'assistant_final_output': None, 'output_status': None,
                  'delivery_provenance': None, 'provider': None, 'model': None, 'classification': {},
                  'attachments': [], 'source': {'type': 'fictional_fixture'},
                  'archived_at': timestamp, 'source_event': event}
        record['record_sha256'] = digest(canon(record))
        path = self.root / 'archive/conversations/2030/04/12' / (b['archive_event_id']+'.json')
        if preserve:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(canon(record))
        return ctx, b, record, path

    def call(self, tool, args, text, channel='telegram'):
        ctx, _, _, _ = self.event(text, channel, tool=tool)
        return self.n.execute(tool, args, ctx)

    def close(self):
        self.n.close()
        self.source.close()

def run_demo(f):
    raw = '记一下，2030年4月12日去虚构的星湾岛旅行，建立星湾岛旅行档案。'
    trip = f.call('nexus_save', {'proposals': [{'domain': 'life', 'title': '星湾岛旅行', 'body': raw,
                  'group_profile': {'name': '星湾岛旅行', 'aliases': ['星湾岛'], 'state': 'open'}}]}, raw)
    gid = trip['results'][0]['item_id']
    expense_text = '记一下，星湾岛旅行午餐花了42元。'
    expense_args = {'proposals': [{'domain': 'life', 'title': '星湾岛午餐', 'body': expense_text, 'group_id': gid,
                    'financial': {'amount_minor': 4200, 'currency': 'CNY', 'direction': 'expense'}}]}
    ctx, _, _, _ = f.event(expense_text, tool='nexus_save')
    expense = f.n.execute('nexus_save', expense_args, ctx)
    replay = f.n.execute('nexus_save', expense_args, ctx)
    item = expense['results'][0]
    daily_text = '生活随手记，星湾岛旅行看到了蓝色风筝。'
    daily = f.call('nexus_save', {'proposals': [{'domain': 'life', 'title': '蓝色风筝', 'body': daily_text,
                   'group_id': gid}]}, daily_text, 'wecom')
    snapshot = f.call('nexus_save', {'proposals': [{'domain': 'life', 'title': '星湾岛汇总', 'summary_for_group': gid}]},
                      '帮我记录，生成星湾岛旅行汇总。')
    correction_text = '刚才星湾岛旅行午餐不是42元，改为38元。'
    corrected = f.call('nexus_update', {'item_id': item['item_id'], 'expected_revision': item['revision_id'],
                       'reason': '纠正虚构午餐金额', 'patch': {'body': correction_text,
                       'financial': {'amount_minor': 3800, 'currency': 'CNY', 'direction': 'expense'}}}, correction_text)
    retrieval = f.call('nexus_query', {'template': 'group_records', 'group_id': gid, 'limit': 1},
                       '查询旧记录，星湾岛旅行记了什么？', 'wecom')
    totals = f.call('nexus_query', {'template': 'group_summary', 'group_id': gid}, '查询星湾岛旅行费用。')
    history = [dict(r) for r in f.n.db.execute('SELECT version,action,body FROM revision WHERE item_id=? ORDER BY version', (item['item_id'],))]
    evidence = [dict(r) for r in f.n.db.execute('SELECT role,quote,start_char,end_char FROM evidence WHERE revision_id=?', (corrected['results'][0]['revision_id'],))]
    return {'fictional': True, 'trip': trip, 'expense': expense, 'replay_idempotent': replay['idempotent'],
            'daily': daily, 'correction': corrected, 'revision_history': history, 'evidence': evidence,
            'relation': [dict(r) for r in f.n.db.execute('SELECT predicate,object_item_id FROM relation WHERE revision_id=?', (corrected['results'][0]['revision_id'],))],
            'retrieval_first_page': retrieval, 'current_totals': totals,
            'old_summary_status': f.n.summary_status(f.n.head(snapshot['results'][0]['item_id'])), 'verify': f.n.verify()}
