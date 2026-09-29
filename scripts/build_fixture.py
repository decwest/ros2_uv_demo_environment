#!/usr/bin/env python3
"""Build a deterministic, dependency-free wheel using only the stdlib."""

import base64
import csv
import hashlib
import io
from pathlib import Path
import sys
import zipfile


def build(workspace):
    info = "venv_only_dep-1.0.0.dist-info"
    files = {
        "venv_only_dep.py": (workspace / "fixtures/venv_only_dep.py").read_bytes(),
        f"{info}/METADATA": (
            "Metadata-Version: 2.1\nName: venv-only-dep\nVersion: 1.0.0\n"
            "Requires-Python: >=3.10\n\nLocal dependency for the ROS demo.\n"
        ).encode(),
        f"{info}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: ros2-uv-demo\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n"
        ).encode(),
    }
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, f"sha256={digest}", len(data)])
    writer.writerow([f"{info}/RECORD", "", ""])
    files[f"{info}/RECORD"] = record.getvalue().encode()
    target = workspace / "vendor/venv_only_dep-1.0.0-py3-none-any.whl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as wheel:
        for name, data in files.items():
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.external_attr = 0o644 << 16
            wheel.writestr(entry, data)
    return target


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
