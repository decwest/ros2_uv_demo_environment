#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-doctor}"
DISTRO="${2:-jazzy}"
CASE="${3:-all}"
BUILD_MODE="${4:-all}"

doctor() {
  local tool
  for tool in docker python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      printf 'Missing prerequisite: %s\n' "$tool" >&2
      return 1
    fi
  done
  if ! docker info >/dev/null 2>&1; then
    printf '%s\n' 'Docker Engine is not reachable.' \
      'Start Docker; on WSL, enable Docker Desktop integration for this distro.' >&2
    return 1
  fi
}

if [[ "$ACTION" == doctor ]]; then
  doctor
  docker version --format 'Docker client {{.Client.Version}} / server {{.Server.Version}}'
  exit
fi

if [[ "$ACTION" == matrix ]]; then
  doctor
  matrix_status=0
  for matrix_distro in jazzy lyrical rolling; do
    if "$0" run "$matrix_distro" "$CASE" "$BUILD_MODE"; then
      :
    else
      rc=$?
      printf '%s finished with status %d; continuing matrix.\n' "$matrix_distro" "$rc" >&2
      matrix_status=1
    fi
  done
  exit "$matrix_status"
fi

case "$ACTION" in build|run|shell) ;; *) printf 'Unknown action: %s\n' "$ACTION" >&2; exit 2 ;; esac
case "$DISTRO" in jazzy|lyrical|rolling) ;; *) printf 'Unknown ROS distro: %s\n' "$DISTRO" >&2; exit 2 ;; esac
case "$CASE" in all|stock|setup-cfg|venv-build|patched|patched-off|system|patched-system) ;; *) printf 'Unknown case: %s\n' "$CASE" >&2; exit 2 ;; esac
case "$BUILD_MODE" in all|install|symlink) ;; *) printf 'Unknown build mode: %s\n' "$BUILD_MODE" >&2; exit 2 ;; esac
doctor

BASE_IMAGE="${BASE_IMAGE:-$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$ROOT_DIR/config/distros.json" "$DISTRO")}"
IMAGE="${DEMO_IMAGE:-ros2-uv-demo:${DISTRO}}"

if [[ -z "${DEMO_IMAGE:-}" || "$ACTION" == build ]]; then
  revision="$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || printf 'uncommitted')"
  build_args=(--build-arg "BASE_IMAGE=$BASE_IMAGE" --build-arg "ROS_DISTRO=$DISTRO" --build-arg "SOURCE_REVISION=$revision")
  if [[ -n "${UV_IMAGE:-}" ]]; then build_args+=(--build-arg "UV_IMAGE=$UV_IMAGE"); fi
  docker build "${build_args[@]}" -f "$ROOT_DIR/docker/Dockerfile" -t "$IMAGE" "$ROOT_DIR"
fi
if [[ "$ACTION" == build ]]; then exit; fi

# Pin this execution to the built image ID, even if another task retags it.
image_id="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
image_distro="$(docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$image_id" | sed -n 's/^ROS_DISTRO=//p')"
if [[ "$image_distro" != "$DISTRO" ]]; then
  printf 'Image ROS_DISTRO=%s does not match requested %s.\n' "$image_distro" "$DISTRO" >&2
  exit 2
fi
run_id="$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}"
work_dir="$ROOT_DIR/.work/$DISTRO/$run_id"
output_dir="$ROOT_DIR/output/$DISTRO/$run_id"
mkdir -p "$work_dir" "$output_dir"
docker image inspect "$image_id" > "$output_dir/image.json"

run_args=(--rm --network none --user "$(id -u):$(id -g)"
  --mount "type=bind,src=$work_dir,dst=/work"
  --mount "type=bind,src=$output_dir,dst=/output")
demo_args=(--distro "$DISTRO" --case "$CASE" --build-mode "$BUILD_MODE")
if [[ "${ALLOW_FALLBACK:-0}" == 1 ]]; then demo_args+=(--allow-fallback); fi
if [[ "$ACTION" == shell ]]; then
  if [[ ! -t 0 || ! -t 1 ]]; then printf 'shell requires a terminal.\n' >&2; exit 2; fi
  run_args+=(-it)
  demo_args+=(--shell)
fi

rc=0
docker run "${run_args[@]}" "$image_id" /usr/bin/python3 /repo/scripts/run_demo.py "${demo_args[@]}" || rc=$?
printf '\nResults: %s\nWorkspace: %s\n' "$output_dir" "$work_dir"
if [[ -f "$output_dir/report.md" ]]; then printf 'Report: %s/report.md\n' "$output_dir"; fi
exit "$rc"
