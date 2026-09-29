#!/usr/bin/env python3
"""Run isolated ROS workspaces and retain evidence for every comparison."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import traceback

REPO = Path(__file__).resolve().parents[1]
CASES = ("stock", "setup-cfg", "venv-build", "patched", "patched-off", "system", "patched-system")
PROBE_PREFIX = "ROS2_UV_PROBE="
AFTER_EDIT = "after-edit-without-rebuild"


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def capture(command, cwd, env, log, timeout=120):
    """A timeout is an infrastructure failure, never an expected import failure."""
    timed_out = False
    with subprocess.Popen(
        command, cwd=cwd, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True,
    ) as process:
        try:
            output, _ = process.communicate(timeout=timeout)
            code = process.returncode
        except subprocess.TimeoutExpired:
            # ros2 launch and colcon spawn children; stop the whole group so a
            # failed case cannot leave nodes running in the next experiment.
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
            code, timed_out = 124, True
            output += "\nDemo command timed out.\n"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(f"$ {shlex.join(map(str, command))}\n{output}\n[exit={code}]\n")
    return {"command": list(map(str, command)), "returncode": code, "timed_out": timed_out, "output": output}


def checked(command, cwd, env, log):
    result = capture(command, cwd, env, log)
    if result["returncode"]:
        raise RuntimeError(f"Command failed ({result['returncode']}), see {log.name}")
    return result


def source_environment(base, setup=None, venv=None):
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c",
         'set -e; if [[ "$1" != - ]]; then source "$1"; fi; '
         'if [[ "$2" != - ]]; then source "$2/bin/activate"; fi; env -0',
         "demo", str(setup) if setup else "-", str(venv) if venv else "-"],
        env=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    return dict(part.decode().split("=", 1) for part in result.stdout.split(b"\0") if part)


def parse_probe(output):
    records = []
    for line in output.splitlines():
        if PROBE_PREFIX in line:
            records.append(json.loads(line.split(PROBE_PREFIX, 1)[1]))
    if len(records) != 1:
        raise ValueError(f"Expected exactly one probe record, got {len(records)}")
    return records[0]


def under(path, directory):
    return Path(path).is_relative_to(directory)


def verify_probe(run, expected_venv, require_dep, revision, *, launch=False):
    """Check the child's evidence, not just ros2 launch's parent exit code."""
    problems = []
    if run["timed_out"]:
        return ["probe timed out"], None
    try:
        probe = parse_probe(run["output"])
        expected_code = 42 if require_dep and expected_venv is None else 0
        allowed_codes = (0, expected_code) if launch else (expected_code,)
        if run["returncode"] not in allowed_codes:
            problems.append(f"unexpected process exit {run['returncode']}")
        if probe["exit_code"] != expected_code:
            problems.append(f"unexpected child exit {probe['exit_code']} (expected {expected_code})")
        if not probe["ros"]["ok"]:
            problems.append("rclpy import or node creation failed")
        if probe["is_venv"] != (expected_venv is not None):
            problems.append("wrong interpreter kind")
        if expected_venv is not None:
            if probe["prefix"] != str(expected_venv):
                problems.append("wrong virtual environment prefix")
            if Path(probe["executable"]).parent != expected_venv / "bin":
                problems.append("interpreter is not from the selected venv")
            if not probe["dependency"]["found"]:
                problems.append("venv-only dependency is missing")
            elif not under(probe["dependency"]["file"], expected_venv):
                problems.append("dependency leaked from outside the selected venv")
            elif probe["dependency"].get("marker") != "venv-only-dep-1.0.0":
                problems.append("wrong dependency contents")
        else:
            if probe["prefix"] != probe["base_prefix"] or probe["executable"] != "/usr/bin/python3":
                problems.append("expected the distro system interpreter")
            if probe["dependency"]["found"]:
                problems.append("venv-only dependency leaked into the system interpreter")
        if probe["revision"] != revision:
            problems.append(f"source revision is {probe['revision']!r}, expected {revision!r}")
    except (ValueError, KeyError, TypeError) as exc:
        return [f"invalid probe evidence: {exc}"], None
    return problems, probe


def create_venv(workspace, env, output, name=".venv"):
    venv = workspace / name
    checked(["uv", "venv", "--python", "/usr/bin/python3", "--system-site-packages", str(venv)],
            workspace, env, output / f"{name}-create.log")
    sync_env = dict(env, UV_PROJECT_ENVIRONMENT=str(venv))
    checked(["uv", "sync", "--frozen", "--offline", "--python", "/usr/bin/python3"],
            workspace, sync_env, output / f"{name}-sync.log")
    return venv


def build_route(workspace):
    logs = list((workspace / "log").glob("build_*/uv_shebang_demo/command.log"))
    commands = "\n".join(path.read_text() for path in logs)
    if re.search(r"setup\.py.*\sdevelop\s", commands):
        return "develop"
    if re.search(r"setup\.py.*\sinstall\s", commands):
        return "install"
    raise RuntimeError("Could not establish the actual build path from colcon command.log")


def expected_interpreter(case, actual_route, venv):
    if case in ("patched", "venv-build") or (case == "setup-cfg" and actual_route == "install"):
        return venv
    return None


def run_case(case, build_mode, work_root, output_root, base):
    key = f"{case}-{build_mode}"
    workspace, output = work_root / key, output_root / key
    output.mkdir(parents=True)
    row = {"case": case, "requested_build": build_mode, "actual_build": "unknown",
           "status": "ERROR", "problems": [], "workspace": str(workspace), "probes": {}}
    try:
        shutil.copytree(REPO / "demos/shebang", workspace)
        use_venv = case not in ("system", "patched-system")
        venv = create_venv(workspace, base, output) if use_venv else None
        if case == "setup-cfg":
            with (workspace / "src/uv_shebang_demo/setup.cfg").open("a") as stream:
                stream.write("\n[build_scripts]\nexecutable = /usr/bin/env python3\n")

        build_env = source_environment(base, venv=venv)
        if case in ("patched", "patched-off", "patched-system"):
            build_env["PYTHONPATH"] = "/opt/colcon-patched:" + build_env.get("PYTHONPATH", "")
        interpreter = str(venv / "bin/python") if case == "venv-build" else "/usr/bin/python3"
        audit_code = (
            "import sys,json,importlib.metadata as m,colcon_core; "
            "print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,"
            "'base_prefix':sys.base_prefix,'colcon_file':colcon_core.__file__,"
            "'colcon_version':m.version('colcon-core'),'setuptools_version':m.version('setuptools')}))"
        )
        audit = checked([interpreter, "-c", audit_code], workspace, build_env, output / "builder.log")
        row["builder"] = json.loads(audit["output"])
        if row["builder"]["executable"] != interpreter:
            raise RuntimeError("Build interpreter does not match the requested interpreter")
        patched = case in ("patched", "patched-off", "patched-system")
        if under(row["builder"]["colcon_file"], Path("/opt/colcon-patched")) != patched:
            raise RuntimeError("Wrong colcon implementation loaded")

        command = [interpreter, "-m", "colcon", "build", "--base-paths", "src",
                   "--event-handlers", "console_direct+"]
        if build_mode == "symlink":
            command.append("--symlink-install")
        if case in ("patched", "patched-system"):
            command += ["--python-shebang", "env"]
        checked(command, workspace, build_env, output / "build.log")
        row["build_command"] = command
        row["actual_build"] = build_route(workspace)
        fallback = build_mode == "symlink" and row["actual_build"] != "develop"
        row["fallback"] = fallback

        script = workspace / "install/uv_shebang_demo/lib/uv_shebang_demo/probe"
        row["shebang"] = script.read_text().splitlines()[0]
        expected_venv = expected_interpreter(case, row["actual_build"], venv)
        if case in ("patched", "patched-system") or (case == "setup-cfg" and row["actual_build"] == "install"):
            expected_shebang = "#!/usr/bin/env python3"
        else:
            expected_shebang = "#!" + interpreter
        if row["shebang"] != expected_shebang:
            row["problems"].append(f"shebang {row['shebang']!r} != {expected_shebang!r}")

        setup = workspace / "install/setup.bash"
        runtime = source_environment(base, setup=setup, venv=venv)
        runtime["DEMO_REQUIRE_DEP"] = "1" if use_venv else "0"
        commands = {
            "run": ["ros2", "run", "uv_shebang_demo", "probe"],
            "launch": ["ros2", "launch", "uv_shebang_demo", "probe.launch.py"],
        }
        for method, invocation in commands.items():
            execution = capture(invocation, workspace, runtime, output / f"{method}.log", timeout=30)
            problems, probe = verify_probe(execution, expected_venv, use_venv, "before-edit", launch=method == "launch")
            row["probes"][method] = probe
            row["problems"] += [f"{method}: {message}" for message in problems]

        revision_file = workspace / "src/uv_shebang_demo/uv_shebang_demo/revision.py"
        revision_file.write_text(f"REVISION = {AFTER_EDIT!r}\n")
        expected_revision = AFTER_EDIT if row["actual_build"] == "develop" else "before-edit"
        execution = capture(commands["run"], workspace, runtime, output / "source-edit.log", timeout=30)
        problems, probe = verify_probe(execution, expected_venv, use_venv, expected_revision)
        row["probes"]["source_edit"] = probe
        row["problems"] += [f"source_edit: {message}" for message in problems]
        row["source_edit_visible"] = bool(probe and probe["revision"] == AFTER_EDIT)

        # The same built installation must follow PATH when another venv is activated.
        if case == "patched":
            other = create_venv(workspace, base, output, name=".other-venv")
            other_env = source_environment(base, setup=setup, venv=other)
            for method, invocation in commands.items():
                execution = capture(invocation, workspace, other_env, output / f"other-venv-{method}.log", timeout=30)
                problems, probe = verify_probe(execution, other, True, expected_revision, launch=method == "launch")
                row["probes"][f"other_venv_{method}"] = probe
                row["problems"] += [f"other_venv_{method}: {message}" for message in problems]

        if row["problems"]:
            row["status"] = "FAIL"
        elif fallback:
            row["status"] = "NOT_COVERED"
        elif use_venv and expected_venv is None:
            row["status"] = "REPRODUCED"
        else:
            row["status"] = "PASS"
    except Exception as exc:
        row["problems"].append(f"{type(exc).__name__}: {exc}")
        (output / "error.log").write_text(traceback.format_exc())
    finally:
        if (workspace / "log").exists():
            shutil.copytree(workspace / "log", output / "colcon-log", symlinks=True)
        save_json(output / "result.json", row)
    return row


def check_default_compatibility(rows):
    """An opt-out patched build must preserve the observed stock behavior."""
    for mode in ("install", "symlink"):
        pair = {row["case"]: row for row in rows if row["requested_build"] == mode}
        if not {"stock", "patched-off"} <= pair.keys():
            continue
        before, after = pair["stock"], pair["patched-off"]
        if before["status"] == "ERROR" or after["status"] == "ERROR":
            continue
        fields = ("actual_build", "shebang", "source_edit_visible")
        if any(before.get(key) != after.get(key) for key in fields):
            after["status"] = "FAIL"
            after["problems"].append("disabled patch changed stock behavior")


def write_report(output, distro, rows):
    save_json(output / "results.json", {"distro": distro, "cases": rows})
    lines = [f"# ROS 2 uv demo — {distro}", "",
             "Measured results. PASS is a verified success; REPRODUCED is a verified missing-venv dependency.",
             "NOT_COVERED means --symlink-install fell back to install; the develop path was not tested.", "",
             "| Case | Requested | Actual | Shebang | Result |",
             "| --- | --- | --- | --- | --- |"]
    for row in rows:
        key = f"{row['case']}-{row['requested_build']}"
        lines.append(f"| [{row['case']}]({key}/result.json) | {row['requested_build']} | "
                     f"{row['actual_build']} | `{row.get('shebang', 'not generated')}` | {row['status']} |")
        # Compatibility checks can update the row after the individual run.
        save_json(output / key / "result.json", row)
    lines += ["", "## Problems", ""]
    issues = [f"- {row['case']}/{row['requested_build']}: {problem}"
              for row in rows for problem in row["problems"]]
    lines += issues or ["None."]
    lines += ["", "See `environment.json`, `sources.json`, `image.json`, and per-case logs for provenance.", ""]
    (output / "report.md").write_text("\n".join(lines))


def environment_report(base, output):
    audit = checked(["/usr/bin/python3", "-c",
                     "import json,sys,importlib.metadata as m; "
                     "print(json.dumps({'python':sys.version,'executable':sys.executable,"
                     "'packages':{n:m.version(n) for n in ['colcon-core','colcon-ros','setuptools']}}))"],
                    REPO, base, output / "environment.log")
    report = json.loads(audit["output"])
    report["utc"] = datetime.now(timezone.utc).isoformat()
    report["ros_distro"] = base["ROS_DISTRO"]
    report["uv"] = subprocess.check_output(["uv", "--version"], text=True).strip()
    report["os_release"] = Path("/etc/os-release").read_text()
    report["patch"] = json.loads(Path("/opt/colcon-patched/provenance.json").read_text())
    actual_patch_hash = hashlib.sha256((REPO / "patches/colcon-core-env-shebang.patch").read_bytes()).hexdigest()
    if report["patch"]["patch_sha256"] != actual_patch_hash:
        raise RuntimeError("The installed patch does not match the repository patch")
    save_json(output / "environment.json", report)
    hashes = {}
    for directory in ("scripts", "docker", "demos", "patches", "config"):
        for path in sorted((REPO / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                hashes[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
    save_json(output / "sources.json", hashes)
    shutil.copy("/opt/demo-packages.tsv", output / "apt-packages.tsv")
    shutil.copy(REPO / "patches/colcon-core-env-shebang.patch", output / "applied.patch")


def open_shell(row, base):
    workspace = Path(row["workspace"])
    if not (workspace / "install/setup.bash").exists():
        raise RuntimeError("No built workspace is available for the shell; see the error log")
    rc = workspace / ".demo.bashrc"
    lines = [f"source {shlex.quote(str(workspace / 'install/setup.bash'))}"]
    if (workspace / ".venv").exists():
        lines.append(f"source {shlex.quote(str(workspace / '.venv/bin/activate'))}")
    if row["case"] in ("patched", "patched-off", "patched-system"):
        lines.append('colcon() { PYTHONPATH="/opt/colcon-patched:${PYTHONPATH:-}" /usr/bin/python3 -m colcon "$@"; }')
    elif row["case"] == "venv-build":
        lines.append(f'colcon() {{ {shlex.quote(str(workspace / ".venv/bin/python"))} -m colcon "$@"; }}')
    lines.append('PS1="(ros2-uv-demo) \\w $ "')
    rc.write_text("\n".join(lines) + "\n")
    os.chdir(workspace)
    print("\nWorkspace ready. The source-edit test has changed revision.py.", flush=True)
    print("Try: ros2 run uv_shebang_demo probe", flush=True)
    if row["case"] in ("patched", "patched-system"):
        print("Build: colcon build --symlink-install --python-shebang env", flush=True)
    os.execvpe("bash", ["bash", "--noprofile", "--rcfile", str(rc), "-i"], base)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distro", choices=("jazzy", "lyrical", "rolling"), default=os.environ.get("ROS_DISTRO"))
    parser.add_argument("--case", choices=("all", *CASES), default="all")
    parser.add_argument("--build-mode", choices=("all", "install", "symlink"), default="all")
    parser.add_argument("--work", type=Path, default=Path("/work"))
    parser.add_argument("--output", type=Path, default=Path("/output"))
    parser.add_argument("--allow-fallback", action="store_true")
    parser.add_argument("--shell", action="store_true")
    args = parser.parse_args()
    if args.distro != os.environ.get("ROS_DISTRO"):
        parser.error("--distro must match the container ROS_DISTRO")
    if args.shell and (args.case == "all" or args.build_mode == "all"):
        parser.error("--shell requires one case and one build mode")
    args.work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    base = dict(os.environ)
    for key in ("VIRTUAL_ENV", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT", "DEMO_REQUIRE_DEP"):
        base.pop(key, None)
    base["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        environment_report(base, args.output)
    except Exception:
        (args.output / "error.log").write_text(traceback.format_exc())
        print(f"Environment validation failed; see {args.output / 'error.log'}", file=sys.stderr)
        return 1
    cases = CASES if args.case == "all" else (args.case,)
    modes = ("install", "symlink") if args.build_mode == "all" else (args.build_mode,)
    rows = []
    for case in cases:
        for mode in modes:
            print(f"\n>>> {args.distro}: {case} / {mode}", flush=True)
            row = run_case(case, mode, args.work, args.output, base)
            rows.append(row)
            print(f"{row['status']} (actual build: {row['actual_build']})", flush=True)
            for problem in row["problems"]:
                print(f"  {problem}", flush=True)
            write_report(args.output, args.distro, rows)
    check_default_compatibility(rows)
    write_report(args.output, args.distro, rows)
    if args.shell:
        open_shell(rows[0], base)
    if any(row["status"] in ("FAIL", "ERROR") for row in rows):
        return 1
    if not args.allow_fallback and any(row["status"] == "NOT_COVERED" for row in rows):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
