"""Regression: a later deletion must never hide unsafe initial history."""
import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

class PrivacyAuditTests(unittest.TestCase):
    def test_history_still_rejects_deleted_synthetic_credential(self):
        script=Path(__file__).resolve().parents[1]/'scripts/privacy_audit.py'
        spec=importlib.util.spec_from_file_location('privacy_audit',script)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);module.ROOT=root
            def git(*args):
                subprocess.run(['git','-C',str(root),*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            git('init','-b','main');git('config','user.name','Nexus contributors')
            git('config','user.email','0+fixture@users.noreply.github.com')
            bad=root/'unsafe.txt';bad.write_text('gh'+'p_'+'a'*30)
            git('add','--','unsafe.txt');git('commit','-m','Synthetic scanner fixture')
            git('rm','--','unsafe.txt');git('commit','-m','Delete synthetic fixture')
            output=io.StringIO()
            with patch.object(sys,'argv',['privacy_audit.py']),contextlib.redirect_stdout(output),self.assertRaises(SystemExit) as caught:
                module.main()
            self.assertEqual(caught.exception.code,1)
            self.assertIn('history:unsafe.txt :: credential',output.getvalue())
            self.assertNotIn('a'*30,output.getvalue())

if __name__=='__main__':unittest.main()
