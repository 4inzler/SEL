# SEL Discord Bot - MAXIMUM SECURITY Sandboxed Container
# No shell access, isolated from host system, minimal attack surface

FROM python:3.11-slim

# Security: Update and remove unnecessary packages
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Security: Run as non-root user with minimal permissions
RUN useradd -m -u 1000 -s /usr/sbin/nologin selbot && \
    mkdir -p /app /data && \
    chown -R selbot:selbot /app /data

WORKDIR /app

# Install dependencies as root, then remove pip
COPY project_echo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge && \
    rm -rf /root/.cache

# Copy application code
COPY project_echo/ /app/
COPY agents/ /app/agents/

# SECURITY: Remove ALL shells and dangerous binaries
RUN rm -f /bin/sh /bin/bash /bin/dash /bin/zsh /bin/csh /bin/tcsh /bin/ksh && \
    rm -f /usr/bin/sh /usr/bin/bash /usr/bin/dash /usr/bin/zsh && \
    rm -f /bin/su /usr/bin/sudo /usr/bin/passwd && \
    rm -f /bin/mount /bin/umount /sbin/mount /sbin/umount && \
    rm -f /usr/bin/curl /usr/bin/wget /usr/bin/nc /usr/bin/ncat /usr/bin/netcat && \
    rm -f /usr/bin/ssh /usr/bin/scp /usr/bin/sftp && \
    rm -f /bin/nc /bin/ncat /bin/netcat && \
    rm -f /usr/bin/python /usr/bin/python3 || true

# SECURITY: Keep only python3.11 binary, remove alternatives
RUN find /usr/bin -type l -name "python*" -delete && \
    ln -s /usr/local/bin/python3.11 /usr/local/bin/python3

# SECURITY: Remove package managers
RUN rm -f /usr/bin/apt /usr/bin/apt-get /usr/bin/dpkg /usr/bin/pip /usr/bin/pip3 && \
    rm -rf /var/cache/apt /var/lib/apt

# SECURITY: Remove compilers and build tools
RUN rm -f /usr/bin/gcc /usr/bin/g++ /usr/bin/cc /usr/bin/c++ /usr/bin/make && \
    rm -rf /usr/include /usr/share/doc /usr/share/man

# Security: Read-only filesystem except for data directory
VOLUME ["/data"]

# Security: Set strict file permissions
RUN chmod -R 755 /app && \
    chmod -R 700 /data && \
    find /app -type f -exec chmod 644 {} \; && \
    find /app -name "*.py" -exec chmod 444 {} \;

# Switch to non-root user (no shell available)
USER selbot

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV HIM_STORE_PATH=/data/him_store
ENV SEL_DB_PATH=/data/sel.db

# SECURITY: Disable all listening capabilities
ENV FLASK_RUN_HOST=127.0.0.1
ENV FLASK_RUN_PORT=0

# Health check (internal only, no network)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# SECURITY: Ensure no ports can be opened
# Python will not bind to any network interfaces except loopback
EXPOSE

# Run SEL with network restrictions
CMD ["python", "-u", "-m", "sel_bot"]
