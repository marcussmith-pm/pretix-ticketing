#!/bin/bash
set -e

# Fix ownership and permissions for Railway volumes
# Railway mounts volumes as root, so we need to change ownership at runtime
if [ -d /data ]; then
    mkdir -p /data/logs /data/media /data/cache /data/profiles
    chmod -R 755 /data /etc/pretix 2>/dev/null || true
fi

# Commands that need to run as root (supervisord manages other processes)
if [ "$1" = "all" ] || [ "$1" = "web" ]; then
    # Fix ownership if we're root
    if [ "$(id -u)" = "0" ]; then
        chown -R pretixuser:pretixuser /data /etc/pretix 2>/dev/null || true
    fi
    # Run supervisord as root (needed to start nginx and manage processes)
    if [ "$(id -u)" = "0" ]; then
        exec /usr/local/bin/pretix "$@"
    else
        exec sudo /usr/local/bin/pretix "$@"
    fi
else
    # Other commands run as pretixuser
    if [ "$(id -u)" = "0" ]; then
        exec sudo -E -u pretixuser /usr/local/bin/pretix "$@"
    else
        exec /usr/local/bin/pretix "$@"
    fi
fi
