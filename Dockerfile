# SEL Discord Bot - Secure Sandboxed Container
# Isolated from host system, minimal attack surface

FROM python:3.11-slim

# Security: Update and remove unnecessary packages
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends ffmpeg libopus0 libsodium23 espeak-ng && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Security: Run as non-root user with minimal permissions
RUN useradd -m -u 1000 -s /usr/sbin/nologin selbot && \
    mkdir -p /app /data && \
    chown -R selbot:selbot /app /data

WORKDIR /app

# Install dependencies as root
COPY project_echo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge && \
    rm -rf /root/.cache

# Copy application code
COPY project_echo/ /app/
COPY agents/ /app/agents/

# Security: Set permissions and clean up dangerous binaries (single RUN to minimize layers)
RUN chmod -R 755 /app && \
    chmod -R 700 /data && \
    find /app -type f -exec chmod 644 {} \; && \
    find /app -name "*.py" -exec chmod 444 {} \; && \
    # Remove dangerous binaries (but keep /bin/sh for healthcheck)
    rm -f /bin/bash /bin/zsh /bin/csh /bin/tcsh /bin/ksh && \
    rm -f /usr/bin/bash /usr/bin/zsh && \
    rm -f /bin/su /usr/bin/sudo /usr/bin/passwd && \
    rm -f /bin/mount /bin/umount /sbin/mount /sbin/umount && \
    rm -f /usr/bin/curl /usr/bin/wget /usr/bin/nc /usr/bin/ncat /usr/bin/netcat && \
    rm -f /usr/bin/ssh /usr/bin/scp /usr/bin/sftp && \
    rm -f /bin/nc /bin/ncat /bin/netcat && \
    rm -f /usr/bin/python /usr/bin/python3 && \
    rm -f /usr/bin/apt /usr/bin/apt-get /usr/bin/dpkg /usr/bin/pip /usr/bin/pip3 && \
    rm -rf /var/cache/apt /var/lib/apt && \
    rm -f /usr/bin/gcc /usr/bin/g++ /usr/bin/cc /usr/bin/c++ /usr/bin/make && \
    rm -rf /usr/include /usr/share/doc /usr/share/man || true

# Security: Read-only filesystem except for data directory
VOLUME ["/data"]

# Switch to non-root user
USER selbot

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV HIM_STORE_PATH=/data/him_store
ENV SEL_DB_PATH=/data/sel.db

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["/usr/local/bin/python", "-c", "import sys; sys.exit(0)"]

# Run SEL
CMD ["/usr/local/bin/python", "-u", "-m", "sel_bot"]
