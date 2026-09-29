#!/usr/bin/env python3
"""Copy the apt colcon module and apply the experiment without changing apt."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

import colcon_core


def main():
    target = Path(sys.argv[1])
    patch = Path(sys.argv[2]).resolve()
    source = Path(colcon_core.__file__).parent
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target / "colcon_core")
    subprocess.run(
        ["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-d", str(target), "-i", str(patch)],
        check=True,
    )
    (target / "provenance.json").write_text(json.dumps({
        "baseline_module": str(source),
        "colcon_core_version": importlib.metadata.version("colcon-core"),
        "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
