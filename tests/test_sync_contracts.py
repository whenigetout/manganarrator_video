import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sync_contracts', Path(__file__).parents[1]/'scripts/sync_contracts.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ContractBootstrapTests(unittest.TestCase):
    def result(self, code=0):
        return SimpleNamespace(returncode=code, stdout='installed/contracts.py')

    @patch.object(module.subprocess, 'run')
    def test_healthy_environment_does_not_install(self, run):
        run.return_value=self.result()
        self.assertEqual(module.ensure_contracts(), 0)
        self.assertEqual(run.call_count, 1)

    @patch.object(module.subprocess, 'run')
    def test_old_contracts_repaired_in_same_interpreter(self, run):
        run.side_effect=[self.result(1),self.result(),self.result()]
        self.assertEqual(module.ensure_contracts(), 0)
        command=run.call_args_list[1].args[0]
        self.assertEqual(command[:3],[module.sys.executable,'-m','pip'])
        self.assertIn('--force-reinstall',command)
        self.assertEqual(run.call_count,3)

    @patch.object(module.subprocess, 'run')
    def test_install_failure_stops(self, run):
        run.side_effect=[self.result(1),self.result(2)]
        self.assertEqual(module.ensure_contracts(),2)
        self.assertEqual(run.call_count,2)

    @patch.object(module.subprocess, 'run')
    def test_shadowing_after_install_is_failure(self, run):
        run.side_effect=[self.result(1),self.result(),self.result(1)]
        self.assertEqual(module.ensure_contracts(),1)
