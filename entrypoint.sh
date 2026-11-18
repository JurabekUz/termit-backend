#!/bin/sh
set -e

echo 'Applying migrations...'
python manage.py migrate --noinput

echo 'Collecting static files...'
python manage.py collectstatic --noinput

echo 'Starting the Django application...'
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    exec gunicorn config.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-4}" \
        --timeout "${GUNICORN_TIMEOUT:-120}" \
        --forwarded-allow-ips="*" \
        --access-logfile - \
        --error-logfile -
fi
