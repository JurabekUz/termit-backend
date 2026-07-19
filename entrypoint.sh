#!/bin/sh

echo 'Applying migrations...'

# Apply database migrations
python manage.py migrate

# Collect static files (if you have STATIC_URL set in Django settings)
python manage.py collectstatic --noinput

echo 'Starting the Django application...'

# Start Django development server
python manage.py runserver 0.0.0.0:8000
