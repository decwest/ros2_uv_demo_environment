"""Emit machine-readable evidence, including evidence on expected failures."""

import json
import os
import sys

from uv_shebang_demo.revision import REVISION


def main():
    result = {
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "is_venv": sys.prefix != sys.base_prefix,
        "module_file": __file__,
        "revision": REVISION,
        "dependency": {"found": False},
        "ros": {"ok": False},
        "exit_code": 0,
    }
    try:
        import venv_only_dep

        result["dependency"] = {
            "found": True,
            "file": venv_only_dep.__file__,
            "marker": venv_only_dep.MARKER,
        }
    except ModuleNotFoundError as exc:
        if exc.name != "venv_only_dep":
            raise
        result["dependency"]["error"] = str(exc)
        if os.environ.get("DEMO_REQUIRE_DEP", "1") == "1":
            result["exit_code"] = 42

    try:
        import rclpy

        rclpy.init()
        try:
            node = rclpy.create_node("uv_shebang_probe")
            node.destroy_node()
            result["ros"] = {"ok": True, "file": rclpy.__file__}
        finally:
            rclpy.shutdown()
    except Exception as exc:
        result["ros"]["error"] = f"{type(exc).__name__}: {exc}"
        result["exit_code"] = 43

    print("ROS2_UV_PROBE=" + json.dumps(result, sort_keys=True), flush=True)
    return result["exit_code"]
