#!/usr/bin/env bash
set -e
KEYS=$(/usr/local/bin/xray x25519)
PUB=$(echo "$KEYS" | grep "Public key"  | awk '{print $3}')
PRV=$(echo "$KEYS" | grep "Private key" | awk '{print $3}')
SID=$(openssl rand -hex 8)
echo "PUB=$PUB"
echo "PRV=$PRV"
echo "SID=$SID"
