FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app/project_echo

COPY project_echo /app/project_echo
RUN apt-get update \
    && apt-get install -y --no-install-recommends playerctl dbus fastfetch \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

RUN chmod +x /app/project_echo/entrypoint.sh

CMD ["/app/project_echo/entrypoint.sh"]
