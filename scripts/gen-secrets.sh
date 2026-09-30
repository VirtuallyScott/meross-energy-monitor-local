#!/usr/bin/env sh
# Generate local secret files for docker compose (SWM-003). Never commit deploy/secrets/.
# Existing files are kept, so re-running is safe. Back up device_cred_key: without it,
# stored device passwords cannot be decrypted (BAK-004).
set -eu
dir="$(cd "$(dirname "$0")/.." && pwd)/deploy/secrets"
mkdir -p "$dir"
chmod 700 "$dir"

make_secret() {
  file="$dir/$1"
  if [ -s "$file" ]; then
    echo "keep     $1"
    return
  fi
  umask 022  # readable by container users; the 700 directory keeps it private on the host
  sh -c "$2" > "$file"
  echo "created  $1"
}

make_secret db_password     "openssl rand -base64 33 | tr -d '/+=\n' | cut -c1-40"
make_secret device_cred_key "openssl rand -base64 32 | tr -d '\n'"
make_secret setup_token     "openssl rand -hex 16 | tr -d '\n'"
echo "Secrets are in $dir"
