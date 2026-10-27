#!/usr/bin/env python3
"""Compare apt-provided and venv-installed colcon using the same ROS fixture."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import traceback

from run_demo import (
    AFTER_EDIT, REPO, build_route, capture, checked, create_venv,
    environment_report, save_json, source_environment, under, verify_probe,
)

WORK = Path('/work')
OUTPUT = Path('/output')
TEMPLATE = WORK / 'venv-colcon-template'
AUDIT = """
import importlib.metadata as m
import importlib.util
import json
import sys
names = ('colcon_core', 'colcon_ros', 'colcon_python_setup_py', 'setuptools')
print(json.dumps({
    'executable': sys.executable,
    'prefix': sys.prefix,
    'base_prefix': sys.base_prefix,
    'modules': {name: importlib.util.find_spec(name).origin for name in names},
    'versions': {name: m.version(name.replace('_', '-')) for name in names},
    'packages': sorted([
        {'name': d.metadata['Name'], 'version': d.version,
         'location': str(d.locate_file(''))}
        for d in m.distributions()
    ], key=lambda d: (d['name'].lower(), d['location'])),
}))
"""


def prepare(base):
    """Resolve once and populate uv's cache for the offline comparison."""
    output = OUTPUT / 'prepare'
    output.mkdir(parents=True)
    shutil.copytree(REPO / 'demos/shebang', TEMPLATE)
    checked(['uv', 'venv', '--python', '/usr/bin/python3',
             '--system-site-packages', str(TEMPLATE / '.venv')],
            TEMPLATE, base, output / 'venv.log')
    # Keep the user's normal dependency resolution; do not preemptively pin
    # setuptools or constrain colcon to match apt.
    checked(['uv', 'add', '--dev', 'colcon-common-extensions'],
            TEMPLATE, base, output / 'uv-add.log')
    for name in ('pyproject.toml', 'uv.lock'):
        shutil.copy(TEMPLATE / name, output / name)
    print('Saved the resolved project and lockfile in /output/prepare.', flush=True)


def audit(interpreter, workspace, env, log):
    return json.loads(checked([str(interpreter), '-c', AUDIT],
                              workspace, env, log)['output'])


def run_case(case, mode, base):
    key = f'{case}-{mode}'
    workspace, output = WORK / key, OUTPUT / key
    output.mkdir(parents=True)
    row = {'case': case, 'requested_build': mode, 'actual_build': 'unknown',
           'status': 'ERROR', 'problems': [], 'probes': {}, 'workspace': str(workspace)}
    try:
        shutil.copytree(REPO / 'demos/shebang', workspace)
        if case == 'venv-colcon':
            for name in ('pyproject.toml', 'uv.lock'):
                shutil.copy(TEMPLATE / name, workspace / name)
        for name in ('pyproject.toml', 'uv.lock'):
            shutil.copy(workspace / name, output / name)
        venv = create_venv(workspace, base, output)
        build_env = source_environment(base, venv=venv)
        cli = Path(shutil.which('colcon', path=build_env['PATH']))
        row['resolved_colcon'] = str(cli)
        row['colcon_cli_shebang'] = cli.read_text().splitlines()[0]
        if case == 'apt-colcon':
            if cli != Path('/usr/bin/colcon'):
                raise RuntimeError(f'Expected apt colcon on PATH, got {cli}')
            interpreter = venv / 'bin/python'
            invocation = [str(interpreter), '-m', 'colcon']
        else:
            if cli != venv / 'bin/colcon':
                raise RuntimeError(f'Expected venv colcon on PATH, got {cli}')
            interpreter = Path(shlex.split(row['colcon_cli_shebang'][2:])[0])
            if interpreter.parent != venv / 'bin':
                raise RuntimeError(f'colcon launcher selects another interpreter: {interpreter}')
            # Exercise ordinary PATH-based invocation, rather than bypassing
            # the installed console script with python -m colcon.
            invocation = ['colcon']

        builder = audit(interpreter, workspace, build_env, output / 'builder.log')
        row['builder'] = builder
        expected_module_root = venv if case == 'venv-colcon' else Path('/usr/lib/python3/dist-packages')
        for name in ('colcon_core', 'colcon_ros', 'colcon_python_setup_py', 'setuptools'):
            if not under(builder['modules'][name], expected_module_root):
                raise RuntimeError(f'{name} came from the wrong installation: {builder["modules"][name]}')
        if builder['prefix'] != str(venv) or builder['executable'] != str(interpreter):
            raise RuntimeError('Build interpreter is not the expected venv Python')

        command = invocation + ['build', '--base-paths', 'src',
                                '--event-handlers', 'console_direct+']
        if mode == 'symlink':
            command.append('--symlink-install')
        row['build_command'] = command
        checked(command, workspace, build_env, output / 'build.log')
        row['actual_build'] = build_route(workspace)
        row['fallback'] = mode == 'symlink' and row['actual_build'] != 'develop'
        script = workspace / 'install/uv_shebang_demo/lib/uv_shebang_demo/probe'
        row['shebang'] = script.read_text().splitlines()[0]
        if row['shebang'] != '#!' + str(interpreter):
            row['problems'].append('Generated script does not select the build interpreter')

        setup = workspace / 'install/setup.bash'
        runtime = source_environment(base, setup=setup, venv=venv)
        without_activation = source_environment(base, setup=setup)
        invocations = {
            'run': ['ros2', 'run', 'uv_shebang_demo', 'probe'],
            'launch': ['ros2', 'launch', 'uv_shebang_demo', 'probe.launch.py'],
        }

        def probe(label, method, env, revision):
            execution = capture(invocations[method], workspace, env,
                                output / f'{label}.log', timeout=30)
            problems, evidence = verify_probe(
                execution, venv, True, revision, launch=method == 'launch')
            row['probes'][label] = evidence
            row['problems'] += [f'{label}: {problem}' for problem in problems]

        for method in invocations:
            probe(method, method, runtime, 'before-edit')
            probe(f'without-activation-{method}', method, without_activation, 'before-edit')

        (workspace / 'src/uv_shebang_demo/uv_shebang_demo/revision.py').write_text(
            f'REVISION = {AFTER_EDIT!r}\n')
        revision = AFTER_EDIT if row['actual_build'] == 'develop' else 'before-edit'
        probe('source-edit', 'run', runtime, revision)
        row['source_edit_visible'] = bool(
            row['probes']['source-edit'] and
            row['probes']['source-edit']['revision'] == AFTER_EDIT)

        checked(['uv', 'sync', '--locked', '--offline', '--python', '/usr/bin/python3'],
                workspace, build_env, output / 'resync.log')
        after = audit(interpreter, workspace, build_env, output / 'builder-after-sync.log')
        if after != builder:
            row['problems'].append('uv sync changed the selected build tools')
        for method in invocations:
            probe(f'after-sync-{method}', method, runtime, revision)

        # Check that the ordinary colcon launcher is still usable after sync.
        checked(invocation + ['list', '--base-paths', 'src'], workspace, build_env,
                output / 'colcon-after-sync.log')
        row['status'] = 'FAIL' if row['problems'] else ('NOT_COVERED' if row['fallback'] else 'PASS')
    except Exception as exc:
        row['problems'].append(f'{type(exc).__name__}: {exc}')
        (output / 'error.log').write_text(traceback.format_exc())
    finally:
        if (workspace / 'log').exists():
            shutil.copytree(workspace / 'log', output / 'colcon-log', symlinks=True)
        save_json(output / 'result.json', row)
    return row


def run(base):
    environment_report(base, OUTPUT)
    before = audit('/usr/bin/python3', REPO, base, OUTPUT / 'system-before.log')
    rows = []
    for case in ('apt-colcon', 'venv-colcon'):
        for mode in ('install', 'symlink'):
            print(f'>>> {case} / {mode}', flush=True)
            row = run_case(case, mode, base)
            rows.append(row)
            print(f'{row["status"]}: {row["actual_build"]}', flush=True)
            for problem in row['problems']:
                print(f'  {problem}', flush=True)
    after = audit('/usr/bin/python3', REPO, base, OUTPUT / 'system-after.log')
    unchanged = before == after
    save_json(OUTPUT / 'results.json', {'cases': rows, 'system_tools_unchanged': unchanged})
    lines = [f'# Venv solutions comparison — {base["ROS_DISTRO"]}', '',
             'Dependencies were resolved once online; all builds and ROS probes ran offline.', '',
             '| Case | Requested | Actual | setuptools | Shebang | Result |',
             '| --- | --- | --- | --- | --- | --- |']
    for row in rows:
        version = row.get('builder', {}).get('versions', {}).get('setuptools', 'unknown')
        key = f'{row["case"]}-{row["requested_build"]}'
        lines.append(f'| [{row["case"]}]({key}/result.json) | {row["requested_build"]} | '
                     f'{row["actual_build"]} | {version} | `{row.get("shebang", "not generated")}` | {row["status"]} |')
    lines += ['', 'PASS requires the selected venv and its dependency, successful rclpy node creation,',
              'ros2 run/launch with and without activation, source-edit behavior, and execution after uv sync.',
              'NOT_COVERED means symlink-install fell back to normal install.', '',
              f'System Python package metadata unchanged: {unchanged}.', '',
              '## Problems', '']
    lines += [f'- {row["case"]}/{row["requested_build"]}: {problem}'
              for row in rows for problem in row['problems']] or ['None.']
    if not unchanged:
        lines.append('- The system Python package audit changed.')
    (OUTPUT / 'report.md').write_text('\n'.join(lines) + '\n')
    if not unchanged or any(row['status'] in ('ERROR', 'FAIL') for row in rows):
        return 1
    return 2 if any(row['status'] == 'NOT_COVERED' for row in rows) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'run'))
    args = parser.parse_args()
    base = dict(os.environ)
    for key in ('VIRTUAL_ENV', 'PYTHONHOME', 'UV_PROJECT_ENVIRONMENT', 'DEMO_REQUIRE_DEP'):
        base.pop(key, None)
    if args.phase == 'prepare':
        prepare(base)
        return 0
    return run(base)


if __name__ == '__main__':
    raise SystemExit(main())
