#!/bin/bash
# Run once on Mac B before python server.py (HTTPS required for browser camera on Mac A)
set -e
cd "$(dirname "$0")"
mkdir -p certs
IP="${1:-100.84.88.110}"
openssl req -x509 -newkey rsa:2048 \
  -keyout certs/key.pem -out certs/cert.pem \
  -days 365 -nodes -subj "/CN=WallSight" \
  -addext "subjectAltName=IP:${IP},IP:127.0.0.1,DNS:localhost"
echo "Created certs/cert.pem and certs/key.pem for IP ${IP}"
