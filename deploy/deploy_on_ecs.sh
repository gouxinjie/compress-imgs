#!/usr/bin/env bash

set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/compress-imgs}"
SOURCE_DIR="${SOURCE_DIR:-$APP_DIR}"
SERVICE_NAME="${SERVICE_NAME:-process-imgs}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MANIFEST_NAME=".deploy-manifest"
CURRENT_MANIFEST="${APP_DIR}/${MANIFEST_NAME}"
NEW_MANIFEST="${SOURCE_DIR}/${MANIFEST_NAME}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1:8000/api/health}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required on ECS but was not found." >&2
  exit 1
fi

if [ ! -d "${SOURCE_DIR}" ]; then
  echo "Source directory not found: ${SOURCE_DIR}" >&2
  exit 1
fi

if [ ! -f "${NEW_MANIFEST}" ]; then
  echo "Missing deploy manifest: ${NEW_MANIFEST}" >&2
  exit 1
fi

mkdir -p "${APP_DIR}"

if [ ! -f "${APP_DIR}/.env" ]; then
  echo "Missing ${APP_DIR}/.env. Create it on ECS before running the workflow." >&2
  exit 1
fi

mkdir -p "${APP_DIR}/work/tmp"

rsync -az \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude 'work/tmp/' \
  --exclude "${MANIFEST_NAME}" \
  "${SOURCE_DIR}/" "${APP_DIR}/"

"${PYTHON_BIN}" - "${APP_DIR}" "${CURRENT_MANIFEST}" "${NEW_MANIFEST}" <<'PY'
from pathlib import Path
import sys

app_dir = Path(sys.argv[1]).resolve()
current_manifest = Path(sys.argv[2])
new_manifest = Path(sys.argv[3])

protected_paths = {
    Path(".env"),
    Path(".venv"),
    Path(".deploy-manifest"),
}
protected_prefixes = (
    Path("work/tmp"),
    Path(".deploy-work"),
)

old_files = set()
if current_manifest.exists():
    old_files = {
        line.strip()
        for line in current_manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

new_files = {
    line.strip()
    for line in new_manifest.read_text(encoding="utf-8").splitlines()
    if line.strip()
}

stale_files = sorted(old_files - new_files)
stale_parents: set[Path] = set()

for rel in stale_files:
    rel_path = Path(rel)
    if rel_path in protected_paths:
        continue
    if any(rel_path == prefix or prefix in rel_path.parents for prefix in protected_prefixes):
        continue

    target = (app_dir / rel_path).resolve()
    try:
        target.relative_to(app_dir)
    except ValueError:
        continue

    if target.is_file():
        target.unlink()
    elif target.exists():
        continue

    parent = rel_path.parent
    while parent != Path("."):
        if parent in protected_paths or any(parent == prefix or prefix in parent.parents for prefix in protected_prefixes):
            break
        stale_parents.add(parent)
        parent = parent.parent

for rel_dir in sorted(stale_parents, key=lambda path: len(path.parts), reverse=True):
    target_dir = (app_dir / rel_dir).resolve()
    try:
        target_dir.relative_to(app_dir)
    except ValueError:
        continue
    try:
        target_dir.rmdir()
    except OSError:
        pass
PY

cp "${NEW_MANIFEST}" "${CURRENT_MANIFEST}"

cd "${APP_DIR}"

if [ ! -d ".venv" ]; then
  "${PYTHON_BIN}" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

sudo -n systemctl restart "${SERVICE_NAME}"
sudo -n systemctl status "${SERVICE_NAME}" --no-pager

for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if .venv/bin/python - "${HEALTHCHECK_URL}" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=5) as response:
    payload = json.load(response)

if payload.get("status") != "ok":
    raise SystemExit(1)
PY
  then
    exit 0
  fi

  if [ "${attempt}" -eq 10 ]; then
    echo "Health check failed: ${HEALTHCHECK_URL}" >&2
    exit 1
  fi

  sleep 2
done
