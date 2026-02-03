#!/bin/bash
set -e

# Fix ownership and permissions for Railway volumes
# Railway mounts volumes as root, so we need to change ownership at runtime
if [ "$(id -u)" = "0" ]; then
    # Running as root - fix permissions
    if [ -d /data ]; then
        mkdir -p /data/logs /data/media /data/cache /data/profiles
        chmod -R 755 /data /etc/pretix 2>/dev/null || true
        chown -R pretixuser:pretixuser /data /etc/pretix 2>/dev/null || true
    fi

    # Execute to main pretix script as pretixuser
    exec sudo -E -u pretixuser /usr/local/bin/pretix "$@"
else
    # Not running as root, just execute main script
    exec /usr/local/bin/pretix "$@"
fi
