"""Real colcon/setuptools tests; no ROS runtime or Docker is required.

These run when colcon and its ROS/bash extensions are available. They exercise
the ament_python build adapter, generated wrappers and editable source imports.
The ROS runtime itself is verified by the Docker matrix, not these tests.
"""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import venv

ROOT = Path(__file__).resolve().parents[1]
HAS_COLCON = all(importlib.util.find_spec(name) for name in ("colcon_core", "colcon_ros", "colcon_bash", "colcon_output"))


@unittest.skipUnless(HAS_COLCON and shutil.which("patch"), "requires colcon-core, colcon-ros, colcon-bash, colcon-output and patch")
class ColconIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import colcon_core

        cls.temporary = tempfile.TemporaryDirectory(prefix="ros2-uv-patch-test-")
        cls.root = Path(cls.temporary.name)
        cls.overlay = cls.root / "patched"
        cls.overlay.mkdir()
        shutil.copytree(Path(colcon_core.__file__).parent, cls.overlay / "colcon_core")
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-d", str(cls.overlay),
                        "-i", str(ROOT / "patches/colcon-core-env-shebang.patch")],
                       check=True, capture_output=True)
        spec = importlib.util.spec_from_file_location("patched_shebang", cls.overlay / "colcon_core/task/python/shebang.py")
        cls.policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.policy)
        cls.runtime = cls.root / "runtime"
        venv.EnvBuilder(system_site_packages=True).create(cls.runtime)
        site = subprocess.check_output([str(cls.runtime / "bin/python"), "-c",
                                        "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip()
        shutil.copy(ROOT / "demos/shebang/fixtures/venv_only_dep.py", Path(site) / "venv_only_dep.py")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_build_matrix(self):
        for case in ("stock", "setup-cfg", "patched", "patched-off"):
            for mode in ("install", "symlink"):
                with self.subTest(case=case, mode=mode):
                    workspace = self.root / f"{case}-{mode}"
                    shutil.copytree(ROOT / "demos/shebang/src", workspace / "src")
                    package = workspace / "src/uv_shebang_demo"
                    (package / "uv_shebang_demo/probe.py").write_text(
                        "import json,sys\nfrom .revision import REVISION\n"
                        "def main():\n"
                        "    try:\n        import venv_only_dep\n        dependency=True\n"
                        "    except ModuleNotFoundError:\n        dependency=False\n"
                        "    print(json.dumps(dict(prefix=sys.prefix,dependency=dependency,revision=REVISION)))\n"
                    )
                    if case == "setup-cfg":
                        with (package / "setup.cfg").open("a") as stream:
                            stream.write("\n[build_scripts]\nexecutable=/usr/bin/env python3\n")
                    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
                    env.pop("PYTHONPATH", None)
                    if case.startswith("patched"):
                        env["PYTHONPATH"] = str(self.overlay)
                    # A venv is active, but the build still uses this test process's interpreter.
                    env["PATH"] = str(self.runtime / "bin") + os.pathsep + env["PATH"]
                    env["VIRTUAL_ENV"] = str(self.runtime)
                    command = [sys.executable, "-m", "colcon", "build", "--base-paths", "src"]
                    if mode == "symlink":
                        command.append("--symlink-install")
                    if case == "patched":
                        command += ["--python-shebang", "env"]
                    result = subprocess.run(command, cwd=workspace, env=env, capture_output=True, text=True, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    script = workspace / "install/uv_shebang_demo/lib/uv_shebang_demo/probe"
                    command_log = "\n".join(p.read_text() for p in (workspace / "log").glob("build_*/uv_shebang_demo/command.log"))
                    self.assertTrue(command_log, "colcon command.log is missing")
                    develop = " develop " in command_log
                    if mode == "symlink" and not develop:
                        self.fail("This integration suite requires legacy develop support; the Docker runner reports fallback separately")
                    use_env = case == "patched" or (case == "setup-cfg" and not develop)
                    self.assertEqual(script.read_text().splitlines()[0],
                                     "#!/usr/bin/env python3" if use_env else "#!" + sys.executable)
                    (package / "uv_shebang_demo/revision.py").write_text('REVISION="edited-without-rebuild"\n')
                    runtime_env = dict(env)
                    runtime_env.pop("PYTHONPATH", None)
                    result = subprocess.run(
                        ["bash", "--noprofile", "--norc", "-c", 'source install/setup.bash && exec "$1"', "test", str(script)],
                        cwd=workspace, env=runtime_env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    evidence = json.loads(result.stdout)
                    self.assertEqual(evidence["dependency"], use_env)
                    self.assertEqual(evidence["prefix"], str(self.runtime) if use_env else sys.prefix)
                    self.assertEqual(evidence["revision"], "edited-without-rebuild" if develop else "before-edit")

    def test_policy_only_changes_declared_wrappers_and_preserves_permissions(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            prefix = Path(directory)
            (prefix / "bin").mkdir()
            script, other = prefix / "bin/probe", prefix / "bin/unrelated"
            script.write_text("#!/usr/bin/python3\nprint('hello')\n")
            script.chmod(0o751)
            other.write_text("#!/bin/sh\necho untouched\n")
            args = SimpleNamespace(path=str(prefix), install_base=str(prefix))
            self.policy.use_env_python(args, {"entry_points": {"console_scripts": ["probe=x:main"]}}, False)
            self.assertEqual(script.read_text(), "#!/usr/bin/env python3\nprint('hello')\n")
            self.assertEqual(script.stat().st_mode & 0o777, 0o751)
            self.assertEqual(other.read_text(), "#!/bin/sh\necho untouched\n")

    def test_policy_refuses_symlinks_and_prefix_escapes(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            prefix = Path(directory)
            (prefix / "bin").mkdir()
            source = prefix / "source.py"
            source.write_text("#!/usr/bin/python3\nprint('source')\n")
            (prefix / "bin/probe").symlink_to(source)
            args = SimpleNamespace(path=str(prefix), install_base=str(prefix))
            metadata = {"entry_points": "[console_scripts]\nprobe=x:main\n"}
            with self.assertRaisesRegex(RuntimeError, "generated entry-point"):
                self.policy.use_env_python(args, metadata, False)
            self.assertTrue(source.read_text().startswith("#!/usr/bin/python3"))
            (prefix / "setup.cfg").write_text("[install]\ninstall_scripts=/outside/prefix\n")
            with self.assertRaisesRegex(RuntimeError, "install prefix"):
                self.policy.use_env_python(args, metadata, False)

    def test_policy_does_not_silently_drop_python_options(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            prefix = Path(directory)
            (prefix / "bin").mkdir()
            script = prefix / "bin/probe"
            contents = "#!/usr/bin/python3 -O\nprint('optimized')\n"
            script.write_text(contents)
            args = SimpleNamespace(path=str(prefix), install_base=str(prefix))
            with self.assertRaisesRegex(RuntimeError, "interpreter options"):
                self.policy.use_env_python(args, {"entry_points": {"console_scripts": ["probe=x:main"]}}, False)
            self.assertEqual(script.read_text(), contents)


if __name__ == "__main__":
    unittest.main()
