"""Small fictional regressions for opt-in, provenance and destructive boundaries."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'examples'))
from fixture import Fixture, run_demo
from extensions.obsidian import mirror
from extensions.obsidian.setup import disable, setup

class ObsidianTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fictional-obsidian-test-')
        self.root = Path(self.temp.name).resolve()
        self.fixture = Fixture(self.root/'fictional-source')
        self.config = {'enabled':True,'database':str(self.root/'fictional-source/data/nexus.sqlite3'),
                       'local_vault':str(self.root/'local/Nexus'),'icloud_vault':None,
                       'include_sensitive':False,'timezone':'UTC'}
        self.state = self.root/'state'
    def tearDown(self):
        self.fixture.close()
        self.temp.cleanup()
    def save(self, title, domain='life'):
        raw = '记一下，'+title+'。'
        return self.fixture.call('nexus_save',{'proposals':[{'domain':domain,'title':title,'body':raw}]},raw)['results'][0]
    def test_skip_enable_later_and_pause_do_not_change_nexus(self):
        settings = self.root/'preferences/settings.json'
        args = argparse.Namespace(language='en',config=str(settings),skip=False,enable=False,
                                  database=self.config['database'],local_vault=self.config['local_vault'],
                                  timezone='UTC',icloud_vault=None,include_sensitive=False)
        before = self.fixture.n.db.execute('SELECT count(*) FROM revision').fetchone()[0]
        result = setup(args,input_fn=lambda _: '',output=lambda _: None)
        self.assertFalse(result['changed'])
        self.assertFalse(settings.exists())
        self.assertFalse(Path(self.config['local_vault']).exists())
        args.enable = True
        result = setup(args,input_fn=lambda _: self.fail('Noninteractive opt-in must not prompt'),output=lambda _: None)
        self.assertTrue(result['enabled'])
        self.assertFalse(result['include_sensitive'])
        self.assertIsNone(result['icloud_vault'])
        self.assertFalse(Path(self.config['local_vault']).exists())
        disable(settings)
        paused = json.loads(settings.read_text())
        self.assertTrue(mirror.run(paused,self.state)['skipped'])
        self.assertFalse(self.state.exists())
        self.assertEqual(before,self.fixture.n.db.execute('SELECT count(*) FROM revision').fetchone()[0])
        self.assertTrue(setup(args,output=lambda _: None)['enabled'])
    def test_grouping_unclassified_and_current_correction(self):
        run_demo(self.fixture)
        self.save('虚构待整理想法','unclassified')
        result = mirror.run(self.config,self.state)
        self.assertEqual(result['errors'],0)
        self.assertEqual(result['unclassified'],1)
        manifest = mirror.managed(Path(self.config['local_vault']))
        group = next(iter(manifest['archives'].values()))
        expected = {r[0] for r in self.fixture.n.db.execute("SELECT i.item_id FROM item i JOIN relation a ON a.revision_id=i.head_revision_id WHERE a.predicate='for_group'")}
        self.assertEqual(set(group['members']),expected)
        for item in expected:
            self.assertTrue(manifest['items'][item]['path'].startswith(group['directory']+'/条目明细/'))
        full = Path(self.config['local_vault'])/group['directory']/'01-完整档案.md'
        self.assertEqual(full.read_text().count('打开明细与原始依据'),len(expected))
        self.assertIn('38 元',full.read_text())
    def test_rename_delete_and_cloud_copy_preserve_user_files(self):
        item = self.save('虚构清风')
        self.config['icloud_vault'] = str(self.root/'cloud/Nexus')
        local = Path(self.config['local_vault']);cloud = Path(self.config['icloud_vault'])
        for vault in (local,cloud):
            (vault/'.obsidian').mkdir(parents=True)
            (vault/'.obsidian/app.json').write_text('{"owned":"user"}')
            (vault/'我的手写笔记.md').write_text('手写内容')
        first = mirror.run(self.config,self.state)
        self.assertEqual(first['cloud'],'成功')
        old = mirror.managed(local)['items'][item['item_id']]['path']
        updated = self.fixture.call('nexus_update',{'item_id':item['item_id'],'expected_revision':item['revision_id'],
                    'reason':'虚构更名','patch':{'title':'虚构清风更名'}},'把虚构清风更名为虚构清风更名。')['results'][0]
        second = mirror.run(self.config,self.state)
        self.assertEqual(second['updated'],1)
        self.assertFalse((local/old).exists());self.assertFalse((cloud/old).exists())
        self.fixture.call('nexus_update',{'item_id':item['item_id'],'expected_revision':updated['revision_id'],
                    'reason':'虚构撤销','patch':{'status':'deleted'}},'删除这条虚构清风更名记录。')
        third = mirror.run(self.config,self.state)
        self.assertEqual(third['removed'],1)
        self.assertEqual(third['cloud'],'成功')
        for vault in (local,cloud):
            self.assertEqual((vault/'.obsidian/app.json').read_text(),'{"owned":"user"}')
            self.assertEqual((vault/'我的手写笔记.md').read_text(),'手写内容')
    def test_cloud_failure_local_only_and_running_lock(self):
        self.save('虚构本地记忆')
        blocked = self.root/'blocked';blocked.write_text('not a directory')
        self.config['icloud_vault'] = str(blocked/'Nexus')
        result = mirror.run(self.config,self.state)
        self.assertEqual(result['local'],'成功');self.assertEqual(result['cloud'],'失败')
        self.assertTrue((Path(self.config['local_vault'])/'00-首页.md').exists())
        result = mirror.run(self.config,self.state,local_only=True)
        self.assertEqual(result['errors'],0);self.assertEqual(result['local'],'成功')
        with (self.state/'sync.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertTrue(mirror.run(self.config,self.state)['skipped'])
    def test_sensitive_opt_in_and_unsafe_target_rejection(self):
        self.save('虚构健康记录','health')
        result = mirror.run(self.config,self.state)
        self.assertEqual(result['exported'],0)
        self.config['include_sensitive'] = True
        result = mirror.run(self.config,self.state)
        self.assertEqual(result['exported'],1)
        with self.assertRaises(ValueError):
            mirror.validate({**self.config,'icloud_vault':self.config['local_vault']})
        with self.assertRaises(ValueError):
            mirror.validate({**self.config,'local_vault':str(mirror.REPO/'Nexus')})
        with self.assertRaises(ValueError):
            mirror.safe(Path(self.config['local_vault']),'../escape.md')
    def test_unowned_collision_and_missing_source_are_not_empty_exports(self):
        self.save('虚构碰撞记录')
        local = Path(self.config['local_vault'])
        local.mkdir(parents=True)
        (local/'00-首页.md').write_text('用户自己的首页')
        result = mirror.run(self.config,self.state)
        self.assertEqual(result['local'],'失败')
        self.assertEqual((local/'00-首页.md').read_text(),'用户自己的首页')
        before = list(local.rglob('*'))
        with self.assertRaises(ValueError):
            mirror.run({**self.config,'database':str(self.root/'absent.sqlite3')},self.state)
        self.assertEqual(before,list(local.rglob('*')))
if __name__ == '__main__':
    unittest.main()
