#!/bin/bash
# EC2 bootstrap: installs Ollama, optionally syncs models from S3, then pulls the target model.
# Template variables substituted by aws_llm_stack.py before injection:
#   __MODEL__           — Ollama model tag to pre-pull (e.g. llama3)
#   __PERSISTENT_BUCKET__ — S3 bucket name, or empty string if not used

set -euo pipefail

MODEL="__MODEL__"
PERSISTENT_BUCKET="__PERSISTENT_BUCKET__"

# ── Install Ollama ────────────────────────────────────────────────────────────
curl -fsSL https://ollama.com/install.sh | sh

systemctl enable ollama
systemctl start ollama

# Wait for Ollama daemon to be ready
for i in $(seq 1 30); do
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

# ── Optional S3 model cache ───────────────────────────────────────────────────
if [ -n "$PERSISTENT_BUCKET" ]; then
    # Restore cached models on startup
    aws s3 sync "s3://${PERSISTENT_BUCKET}/models/" /root/.ollama/models/ || true

    # Systemd shutdown hook to persist models back to S3
    cat > /etc/systemd/system/ollama-s3-sync.service << EOF
[Unit]
Description=Sync Ollama models to S3 on shutdown
DefaultDependencies=no
Before=shutdown.target reboot.target halt.target
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStop=/usr/bin/aws s3 sync /root/.ollama/models/ s3://${PERSISTENT_BUCKET}/models/
TimeoutStopSec=600

[Install]
WantedBy=multi-user.target
EOF
    systemctl enable ollama-s3-sync
    systemctl start ollama-s3-sync
fi

# ── Pre-pull the configured model (background; SSH available immediately) ─────
nohup ollama pull "$MODEL" >> /var/log/ollama-pull.log 2>&1 &

echo "Bootstrap complete. Model pull running in background — check /var/log/ollama-pull.log"
