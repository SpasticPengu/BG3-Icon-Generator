#!/bin/sh
# BG3 Icon Generator (D47 / D48): ./start.sh on Linux; on macOS double-click Start.command. The first start sets up the
# app's own Python and libraries in .runtime/ (about 300 MB, needs the internet once; nothing is installed elsewhere).
# Each start brings the libraries in line with requirements.lock (an update may change them); exit code 75 = the editor
# installed an update and wants a restart. Delete .runtime/ to set it all up again.
cd "$(dirname "$0")" || exit 1
RT="$PWD/.runtime"
UV="$RT/uv/uv"
export UV_CACHE_DIR="$RT/cache" UV_PYTHON_INSTALL_DIR="$RT/python"
fail() { echo; echo "Setting up failed (see above). Check the internet connection and start again; deleting .runtime starts the setup over."; exit 1; }
if [ ! -x "$UV" ]; then
  echo "First start: downloading uv, which sets up the app's own Python..."
  curl -LsSf https://astral.sh/uv/0.12.18/install.sh | env UV_UNMANAGED_INSTALL="$RT/uv" sh || fail
  [ -x "$UV" ] || fail
fi
if [ ! -x "$RT/env/bin/python" ]; then
  echo "First start: setting up Python and the libraries, about a minute..."
  "$UV" venv "$RT/env" --managed-python --python 3.12 --quiet || fail
fi
while :; do
  "$UV" pip sync requirements.lock --python "$RT/env/bin/python" --require-hashes --quiet || fail
  ICONGEN_LAUNCHER=1 "$RT/env/bin/python" -m iconkit.editor "$@"
  code=$?
  [ "$code" -eq 75 ] || exit "$code"
done
