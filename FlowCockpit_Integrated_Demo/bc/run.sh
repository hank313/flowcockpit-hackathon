#!/usr/bin/env bash
set -euo pipefail
audio_project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$audio_project_dir/.venv/bin/python" ]]; then
  python3 -m venv "$audio_project_dir/.venv"
fi
if ! cmp -s "$audio_project_dir/requirements.txt" "$audio_project_dir/.venv/.audio-json-requirements"; then
  "$audio_project_dir/.venv/bin/python" -m pip install -r "$audio_project_dir/requirements.txt" >&2
  cp "$audio_project_dir/requirements.txt" "$audio_project_dir/.venv/.audio-json-requirements"
fi
if [[ $# -eq 0 ]]; then
  set -- --serve
fi
exec "$audio_project_dir/.venv/bin/python" "$audio_project_dir/app.py" "$@"
