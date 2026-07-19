FROM python:3.11.4-alpine

WORKDIR /user/app/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install dependencies
RUN apk update && apk add --no-cache \
    gdal gdal-dev \
    geos geos-dev \
    postgresql-libs \
    gcc musl-dev postgresql-dev python3-dev\
    gettext

# Upgrade pip
RUN pip install --upgrade pip

# Copy and install Python dependencies
COPY requirements.txt /user/app/requirements.txt
RUN pip install -r requirements.txt

# Copy entrypoint script and make it executable
COPY entrypoint.sh /user/app/entrypoint.sh
RUN chmod +x /user/app/entrypoint.sh

# Copy application source code
COPY . /user/app

# Set entrypoint
ENTRYPOINT ["sh", "/user/app/entrypoint.sh"]
