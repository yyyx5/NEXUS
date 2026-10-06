import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'examples'))
from fixture import Fixture, run_demo
from core import Core
from binding import Denied
from base import Conflict, canon
from backup import verified_backup

class NexusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.f = Fixture(self.temp.name)
    def tearDown(self):
        self.f.close()
        self.temp.cleanup()
    def save(self, text='记一下，虚构日常。', **extra):
        args = {'proposals': [{'domain': 'life', 'title': '虚构日常', 'body': text, **extra}]}
        ctx, b, r, p = self.f.event(text, tool='nexus_save')
        return self.f.n.execute('nexus_save', args, ctx), args, ctx
    def test_demo_history_relation_totals_and_stale_summary(self):
        result = run_demo(self.f)
        self.assertEqual(result['verify']['errors'], [])
        self.assertTrue(result['replay_idempotent'])
        self.assertEqual([h['version'] for h in result['revision_history']], [1, 2])
        self.assertEqual(result['current_totals']['totals'][0]['total_minor'], 3800)
        self.assertEqual(result['relation'][0]['predicate'], 'for_group')
        self.assertEqual({e['role'] for e in result['evidence']}, {'supports', 'corrects'})
        self.assertIsNotNone(result['retrieval_first_page']['next_cursor'])
        self.assertTrue(result['old_summary_status']['needs_update'])
    def test_both_channels_use_trusted_tool_ancestry(self):
        for channel in ('telegram', 'wecom'):
            ctx, _, _, _ = self.f.event('生活随手记，虚构风筝。', channel, tool='nexus_save')
            result = self.f.n.execute('nexus_save', {'proposals': [{'domain': 'life', 'body': '虚构风筝'}]}, ctx)
            self.assertTrue(result['committed'])
    def test_wrong_owner_agent_account_group_and_session_denied(self):
        ctx, _, _, _ = self.f.event('记一下，虚构。')
        for key, value in [('agentId','other'),('accountId','other'),('senderIsOwner',False),('requesterSenderId','stranger'),('sessionKey','agent:demo-agent:subagent:x')]:
            with self.subTest(key=key), self.assertRaises(Denied):
                self.f.n.binder.native({**ctx, key: value})
        self.f.source.execute("UPDATE conversations SET kind='group'"); self.f.source.commit()
        with self.assertRaises(Denied): self.f.n.binder.native(ctx)
    def test_archive_tamper_rejected(self):
        ctx, b, r, p = self.f.event('记一下，虚构。')
        r['original_user_text'] = 'tampered'; p.write_text(canon(r))
        with self.assertRaises(Denied): self.f.n.binder.archive(b)
    def test_pending_survives_restart_then_commits_once(self):
        ctx, b, r, p = self.f.event('记一下，虚构等待。', preserve=False, tool='nexus_save')
        args = {'proposals': [{'domain': 'life', 'body': '虚构等待'}]}
        self.assertFalse(self.f.n.execute('nexus_save', args, ctx)['committed'])
        self.f.n.close(); self.f.n = Core(self.f.root/'data/nexus.sqlite3', self.f.settings)
        p.parent.mkdir(parents=True); p.write_text(canon(r)); self.f.n.reconcile(); self.f.n.reconcile()
        self.assertEqual(self.f.n.db.execute("SELECT status FROM pending_intent").fetchone()[0], 'completed')
        self.assertEqual(self.f.n.db.execute('SELECT count(*) FROM item').fetchone()[0], 1)
    def test_fallback_upgraded_without_duplicate(self):
        ctx, b, r, _ = self.f.event('生活随手记，虚构风筝。')
        fallback = self.f.n.fallback(b, r)
        saved = self.f.n.execute('nexus_save', {'proposals': [{'domain':'life','title':'风筝','body':'虚构风筝'}]}, ctx)
        self.assertEqual(fallback['item_id'], saved['results'][0]['item_id'])
        self.assertEqual(saved['results'][0]['version'], 2)
    def test_transaction_rolls_back_bad_batch(self):
        ctx, _, _, _ = self.f.event('记一下，虚构。')
        with self.assertRaises(ValueError):
            self.f.n.execute('nexus_save', {'proposals':[{'domain':'life','body':'虚构'}, {'domain':'life','quote':'absent'}]}, ctx)
        for table in ('item','source','revision','operation'):
            self.assertEqual(self.f.n.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
    def test_stale_correction_rejected(self):
        saved, _, _ = self.save(); item = saved['results'][0]
        args = {'item_id':item['item_id'],'expected_revision':item['revision_id'],'reason':'虚构纠错','patch':{'body':'虚构更正'}}
        self.f.call('nexus_update', args, '刚才改为虚构更正。')
        with self.assertRaises(Conflict): self.f.call('nexus_update', args, '再次纠正虚构。')
        self.assertEqual(self.f.n.head(item['item_id'])['version'],2)
    def test_idempotency_conflicting_request_rejected(self):
        saved, args, ctx = self.save()
        args['proposals'][0]['title'] = 'changed'
        with self.assertRaises(Conflict): self.f.n.execute('nexus_save',args,ctx)
    def test_immutable_rows_and_quote_spans(self):
        saved, _, _ = self.save()
        with self.assertRaises(sqlite3.IntegrityError): self.f.n.db.execute("UPDATE source SET raw_text='changed'")
        with self.assertRaises(sqlite3.IntegrityError): self.f.n.db.execute("DELETE FROM revision")
        with self.assertRaises(ValueError): self.f.n.evidence(saved['source_id'],'absent')
    def test_health_hidden_from_ordinary_queries(self):
        self.save('记一下，虚构健康记录。', domain='health', body='虚构健康记录。')
        ordinary = self.f.call('nexus_search', {'text':'虚构'}, '查询日常虚构记录。')
        self.assertEqual(ordinary['hits'], [])
        health = self.f.call('nexus_search', {'domain':'health'}, '查询虚构健康记录。')
        self.assertEqual(len(health['hits']),1)
    def test_undated_source_cannot_gain_date(self):
        with self.assertRaises(ValueError): self.save(valid_from='2030-04-12')
    def test_ai_inference_cannot_be_fact(self):
        with self.assertRaises(ValueError): self.save(assertion_kind='ai_inference')
    def test_cursor_invalidated_after_write(self):
        for _ in range(3): self.save()
        args = {'template':'records_by_period','domain':'life','limit':1}
        first = self.f.call('nexus_query',args,'查询生活记录。')
        self.save()
        with self.assertRaises(Conflict): self.f.call('nexus_query',{**args,'cursor':first['next_cursor']},'查询下一页。')
    def test_fts_and_backup_restore(self):
        self.save('记一下，虚构蓝色风筝。')
        self.assertEqual(len(self.f.n.search('蓝色风筝')['hits']),1)
        receipt = verified_backup(self.f.n,self.f.root)
        restored = Core(receipt['path'],self.f.settings)
        try: self.assertEqual(restored.verify()['errors'],[])
        finally: restored.close()
    def test_source_database_unchanged_by_nexus_read(self):
        ctx, _, _, _ = self.f.event('查询虚构记录。', tool='nexus_search')
        before = Path(self.f.settings['sourceDB']).read_bytes()
        self.f.n.execute('nexus_search',{},ctx)
        self.assertEqual(before,Path(self.f.settings['sourceDB']).read_bytes())

    def test_task_completion_retains_history(self):
        saved, _, _ = self.save('记一下，确定要整理虚构书架。', task={'state':'open'})
        item=saved['results'][0]
        self.f.call('nexus_update', {'item_id':item['item_id'],'expected_revision':item['revision_id'],
                    'reason':'虚构任务完成','patch':{'task':{'state':'done'}}}, '虚构书架整理已完成。')
        self.assertEqual(self.f.n.query('open_tasks'),[])
        states=[r[0] for r in self.f.n.db.execute('SELECT state FROM task_detail')]
        self.assertEqual(states,['open','done'])
    def test_schedule_cancel_keeps_original_without_task(self):
        title='虚构星湾预约'
        text='记一下，2030年4月13日的虚构星湾预约。'
        saved, _, _ = self.save(text,title=title,temporal_status='planned',schedule={
            'start_date':'2030-04-13','time_expression':'2030年4月13日'})
        item=saved['results'][0]
        result=self.f.call('nexus_update',{'item_id':item['item_id'],'expected_revision':item['revision_id'],
            'reason':'虚构取消','patch':{'status':'deleted'}},'取消虚构星湾预约。')
        self.assertEqual(result['receipts'][0]['schedule_state'],'cancelled')
        self.assertEqual(self.f.n.db.execute('SELECT count(*) FROM task_detail').fetchone()[0],0)
        self.assertEqual(self.f.n.db.execute('SELECT count(*) FROM schedule_detail').fetchone()[0],2)
        self.assertEqual(self.f.call('nexus_query',{'template':'upcoming_schedules','start':'2030-04-01'},'查询未来日程。')['total'],0)
    def test_entity_alias_and_relation_are_versioned(self):
        ctx, _, _, _=self.f.event('记一下，虚构人物风铃的别名是纸鹤。')
        result=self.f.n.execute('nexus_save',{'proposals':[
            {'domain':'life','body':'虚构人物风铃'},
            {'kind':'entity','domain':'life','title':'风铃','aliases':['纸鹤']}]},ctx)
        entity=result['results'][1]
        self.assertEqual(self.f.n.lookup_alias('纸鹤')[0]['entity_item_id'],entity['item_id'])

if __name__ == '__main__': unittest.main()
