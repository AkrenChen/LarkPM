import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINKIN = ROOT.parent / 'LinkinNotes'
import sys
sys.path.insert(0, str(ROOT / 'backend'))


class LinkinBridgeTests(unittest.TestCase):
    def test_bridge_can_edit_linked_task_and_note_without_native_connection(self):
        from workspace import Workspace
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, LARKPM_DATA_DIR=directory):
            w = Workspace()
            task = w.create({'title': '来自需求', 'owners': [{'id': 'me', 'name': '我'}]})
            task = w.link(task['id'], task['revision'])
            spec = importlib.util.spec_from_file_location('pm_api', LINKIN / 'backend' / 'pm_api.py')
            self.assertIsNotNone(spec)
            module = importlib.util.module_from_spec(spec)
            import sys
            sys.path.insert(0, str(LINKIN / 'backend'))
            try:
                spec.loader.exec_module(module)
                module.call('pm_edit', {'id': task['id'], 'patch': {'state': 'done', 'end': '2026-11-20'}, 'revision': task['revision']})
                module.call('pm_note', {'id': task['id'], 'text': '我的私人笔记', 'revision': 0})
                self.assertEqual(w.get(task['id'])['state'], 'done')
                self.assertEqual(module.call('pm_snapshot', {})['tasks'][0]['note'], '我的私人笔记')
                self.assertNotIn('我的私人笔记', str(w.snapshot()))
                child = module.call('pm_branch', {'id': task['id'], 'title': '后续分支'})
                self.assertTrue(child['linked'])
                self.assertIsNone(child['source'])
            finally:
                sys.path.pop(0)
                w.close()
