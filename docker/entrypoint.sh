#!/usr/bin/env bash
set -eo pipefail
mkdir -p "$HOME" "$UV_CACHE_DIR"
source "/opt/ros/${ROS_DISTRO}/setup.bash"
exec "$@"
