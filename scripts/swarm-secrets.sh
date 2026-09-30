#!/usr/bin/env sh
# Create Docker Swarm secrets from deploy/secrets/ (run gen-secrets.sh first).
# Secrets are immutable in Swarm; to rotate, create a new name and update the stack.
set -eu
dir="$(cd "$(dirname "$0")/.." && pwd)/deploy/secrets"
for name in db_password device_cred_key setup_token; do
  if docker secret inspect "energy_${name}" >/dev/null 2>&1; then
    echo "exists   energy_${name}"
  else
    docker secret create "energy_${name}" "$dir/$name" >/dev/null
    echo "created  energy_${name}"
  fi
done
