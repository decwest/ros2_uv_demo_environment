#!/usr/bin/env bash
# Resolve tools once online, then compare both solutions without network access.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${DEMO_IMAGE:-ros2-uv-demo:jazzy}"
image_id="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
distro="$(docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$image_id" | sed -n 's/^ROS_DISTRO=//p')"
if [[ -z "$distro" ]]; then
  printf 'The image must be a prepared ROS 2 uv demo image.\n' >&2
  exit 2
fi
run_id="$(date -u +%Y%m%dT%H%M%SZ)-venv-solutions-${RANDOM}"
work_dir="$ROOT_DIR/.work/$distro/$run_id"
output_dir="$ROOT_DIR/output/$distro/$run_id"
mkdir -p "$work_dir" "$output_dir"
docker image inspect "$image_id" > "$output_dir/image.json"
run_args=(--rm --user "$(id -u):$(id -g)"
  --env UV_CACHE_DIR=/work/uv-cache
  --mount "type=bind,src=$ROOT_DIR,dst=/repo,readonly"
  --mount "type=bind,src=$work_dir,dst=/work"
  --mount "type=bind,src=$output_dir,dst=/output")

printf 'Preparing colcon dependencies from PyPI...\n'
if ! docker run --network bridge "${run_args[@]}" "$image_id" \
  /usr/bin/python3 /repo/scripts/compare_venv_solutions.py prepare; then
  printf 'Preparation failed. Logs: %s\n' "$output_dir" >&2
  exit 1
fi

rc=0
docker run --network none "${run_args[@]}" "$image_id" \
  /usr/bin/python3 /repo/scripts/compare_venv_solutions.py run || rc=$?
printf '\nResults: %s\nWorkspace: %s\n' "$output_dir" "$work_dir"
exit "$rc"
