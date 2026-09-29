import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


runner = module("run_demo")
fixture = module("build_fixture")


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.venv = Path("/work/example/.venv")
        self.probe = {
            "executable": str(self.venv / "bin/python3"), "prefix": str(self.venv),
            "base_prefix": "/usr", "is_venv": True, "revision": "before-edit",
            "dependency": {"found": True, "marker": "venv-only-dep-1.0.0",
                           "file": str(self.venv / "lib/python3.12/site-packages/venv_only_dep.py")},
            "ros": {"ok": True}, "exit_code": 0,
        }

    def execution(self, probe=None, returncode=0, timed_out=False):
        return {"returncode": returncode, "timed_out": timed_out,
                "output": "[probe-1] ROS2_UV_PROBE=" + json.dumps(probe or self.probe)}

    def test_launch_child_failure_cannot_hide_behind_successful_parent(self):
        self.probe["exit_code"] = 43
        self.probe["ros"] = {"ok": False, "error": "cannot import rclpy"}
        problems, _ = runner.verify_probe(self.execution(), self.venv, True, "before-edit", launch=True)
        self.assertIn("rclpy import or node creation failed", problems)
        self.assertTrue(any("child exit" in message for message in problems))

    def test_expected_missing_dependency_is_verified_precisely(self):
        self.probe.update(executable="/usr/bin/python3", prefix="/usr", is_venv=False, exit_code=42)
        self.probe["dependency"] = {"found": False}
        problems, _ = runner.verify_probe(self.execution(returncode=42), None, True, "before-edit")
        self.assertEqual(problems, [])
        self.probe["ros"]["ok"] = False
        problems, _ = runner.verify_probe(self.execution(returncode=42), None, True, "before-edit")
        self.assertTrue(problems)

    def test_success_requires_the_selected_venv_and_its_dependency(self):
        problems, _ = runner.verify_probe(self.execution(), self.venv, True, "before-edit")
        self.assertEqual(problems, [])
        self.probe["prefix"] = "/work/another/.venv"
        self.probe["dependency"]["file"] = "/usr/lib/python3/dist-packages/venv_only_dep.py"
        problems, _ = runner.verify_probe(self.execution(), self.venv, True, "before-edit")
        self.assertIn("wrong virtual environment prefix", problems)
        self.assertIn("dependency leaked from outside the selected venv", problems)

    def test_timeout_and_missing_duplicate_or_corrupt_evidence_fail(self):
        problems, _ = runner.verify_probe(self.execution(timed_out=True), self.venv, True, "before-edit")
        self.assertEqual(problems, ["probe timed out"])
        for output in ("", "ROS2_UV_PROBE={", self.execution()["output"] * 2):
            with self.subTest(output=output):
                execution = self.execution()
                execution["output"] = output
                problems, _ = runner.verify_probe(execution, self.venv, True, "before-edit")
                self.assertTrue(problems)

    def test_source_edit_must_really_be_visible(self):
        problems, _ = runner.verify_probe(self.execution(), self.venv, True, runner.AFTER_EDIT)
        self.assertTrue(any("source revision" in message for message in problems))

    def test_disabled_patch_regression_is_detected(self):
        stock = {"case": "stock", "requested_build": "symlink", "actual_build": "develop",
                 "shebang": "#!/usr/bin/python3", "status": "REPRODUCED", "problems": [],
                 "source_edit_visible": True}
        disabled = copy.deepcopy(stock)
        disabled.update(case="patched-off", shebang="#!/usr/bin/env python3")
        runner.check_default_compatibility([stock, disabled])
        self.assertEqual(disabled["status"], "FAIL")


class FixtureTests(unittest.TestCase):
    def test_committed_wheel_matches_source_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "fixtures").mkdir()
            source = ROOT / "demos/shebang/fixtures/venv_only_dep.py"
            (workspace / "fixtures/venv_only_dep.py").write_bytes(source.read_bytes())
            first = fixture.build(workspace).read_bytes()
            self.assertEqual(first, fixture.build(workspace).read_bytes())
            self.assertEqual(first, (ROOT / "demos/shebang/vendor/venv_only_dep-1.0.0-py3-none-any.whl").read_bytes())
            with zipfile.ZipFile(fixture.build(workspace)) as wheel:
                self.assertEqual(wheel.read("venv_only_dep.py"), source.read_bytes())
                self.assertIsNone(wheel.testzip())


if __name__ == "__main__":
    unittest.main()
