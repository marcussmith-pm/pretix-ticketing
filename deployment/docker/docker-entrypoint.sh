#!/bin/bash
set -e

cd /pretix/src
export DJANGO_SETTINGS_MODULE=production_settings
export DATA_DIR=/data/
export HOME=/pretix
export AUTOMIGRATE=${AUTOMIGRATE:-yes}
# Use environment variable or default to 2 (don't auto-calculate based on CPU count)
export NUM_WORKERS=${NUM_WORKERS:-2}

# Create data directories
mkdir -p /data/logs /data/media /data/cache /data/profiles 2>/dev/null || true
chmod -R 755 /data /etc/pretix 2>/dev/null || true
chown -R pretixuser:pretixuser /data /etc/pretix 2>/dev/null || true

# Run migrations
if [ "$AUTOMIGRATE" != "skip" ]; then
  python3 -m pretix migrate --noinput
fi

# Handle different commands
if [ "$1" = "all" ]; then
    # Run supervisord directly (needs root to start nginx)
    exec /usr/bin/supervisord -n -c /etc/supervisord.all.conf
fi

if [ "$1" = "web" ]; then
    # Run supervisord for web only
    exec /usr/bin/supervisord -n -c /etc/supervisord.web.conf
fi

if [ "$1" = "cron" ]; then
    exec python3 -m pretix runperiodic
fi

if [ "$1" = "webworker" ]; then
    exec gunicorn pretix.wsgi \
        --name pretix \
        --workers $NUM_WORKERS \
        --max-requests 1200 \
        --max-requests-jitter 50 \
        --log-level=info \
        --bind=unix:/tmp/pretix.sock
fi

if [ "$1" = "taskworker" ]; then
    shift
    exec celery -A pretix.celery_app worker -l info "$@"
fi

if [ "$1" = "upgrade" ]; then
    exec python3 -m pretix updateassets
fi

# Default: run pretix command as pretixuser
exec sudo -E -u pretixuser python3 -m pretix "$@"
