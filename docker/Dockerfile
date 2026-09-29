# syntax=docker/dockerfile:1
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.28
ARG BASE_IMAGE=ros:jazzy-ros-base-noble
FROM ${UV_IMAGE} AS uv
FROM ${BASE_IMAGE}

ARG ROS_DISTRO=jazzy
ARG SOURCE_REVISION=uncommitted
LABEL org.opencontainers.image.source="https://github.com/decwest/ros2_uv_demo_environment" \
      org.opencontainers.image.revision="${SOURCE_REVISION}"

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system \
    UV_LINK_MODE=copy \
    ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
    HOME=/tmp/demo-home \
    UV_CACHE_DIR=/tmp/demo-uv-cache

# Refresh the whole underlay together. Updating rclpy alone can mix Rolling
# packages from different syncs and leave unresolved symbols in its C extension.
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
      patch python3-colcon-common-extensions python3-setuptools python3-venv \
      ros-${ROS_DISTRO}-rclpy ros-${ROS_DISTRO}-ros2run ros-${ROS_DISTRO}-ros2launch \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
COPY . /repo
RUN /usr/bin/python3 /repo/scripts/prepare_colcon.py \
      /opt/colcon-patched /repo/patches/colcon-core-env-shebang.patch \
    && /bin/bash -c 'source /opt/ros/${ROS_DISTRO}/setup.bash && /usr/bin/python3 -c "import rclpy; import ros2cli.cli"' \
    && dpkg-query -W > /opt/demo-packages.tsv \
    && chmod +x /repo/docker/entrypoint.sh

WORKDIR /work
ENTRYPOINT ["/repo/docker/entrypoint.sh"]
CMD ["/usr/bin/python3", "/repo/scripts/run_demo.py"]
