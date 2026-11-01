#!/usr/bin/env bash
# Build libpostal from source (no root needed) and install the `postal`
# Python binding into the project venv. Required for the Abbreviation layer
# of the error taxonomy; without it the classifier refuses to run.
#
# Env overrides (all optional):
#   LIBPOSTAL_PREFIX  install prefix for the C library   (default: $HOME/.local)
#   LIBPOSTAL_DATA    where the ~2 GB model data goes     (default: $PREFIX/share/libpostal)
#   LIBPOSTAL_SRC     where to clone the source           (default: $HOME/.cache/libpostal-src)
#   VENV_PY           python of the venv to install into  (default: <this dir>/.venv/bin/python)
#
# Needs: gcc, make, autoconf, automake, libtoolize, pkg-config, curl, git.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${LIBPOSTAL_PREFIX:-$HOME/.local}"
DATADIR="${LIBPOSTAL_DATA:-$PREFIX/share/libpostal}"
SRC="${LIBPOSTAL_SRC:-$HOME/.cache/libpostal-src}"
VENV_PY="${VENV_PY:-$HERE/.venv/bin/python}"
JOBS="$(nproc 2>/dev/null || echo 4)"

for t in gcc make autoconf automake libtoolize pkg-config curl git; do
  command -v "$t" >/dev/null || { echo "missing build tool: $t" >&2; exit 1; }
done
[ -x "$VENV_PY" ] || { echo "venv python not found at $VENV_PY (create the venv first)" >&2; exit 1; }

mkdir -p "$PREFIX" "$DATADIR"

if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 https://github.com/openvenues/libpostal "$SRC"
fi
cd "$SRC"
./bootstrap.sh
./configure --prefix="$PREFIX" --datadir="$DATADIR"
make -j"$JOBS"
make install            # also downloads the model data into $DATADIR (~2 GB, once)

# Python binding, linked against the prefix above with an rpath so no
# LD_LIBRARY_PATH is needed at runtime.
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
# PIP_USER=0 overrides a global `pip config` of user=true, which a venv rejects.
PIP_USER=0 CFLAGS="-I$PREFIX/include" LDFLAGS="-L$PREFIX/lib -Wl,-rpath,$PREFIX/lib" \
  "$VENV_PY" -m pip install --no-cache-dir --force-reinstall postal

# The per-language dictionaries. The Python binding never exposes these, but
# the Abbreviation layer needs them: without them coverage is English-shaped
# and every non-English abbreviation ("C/", "al.", "ul.", "Avda.") is
# mislabelled. They are plain text, ~2 MB, and live only in the source tree,
# so copy them next to the classifier where it looks by default.
DICT_SRC="$SRC/resources/dictionaries"
DICT_DST="$HERE/error_taxonomy/libpostal_dictionaries"
if [ -d "$DICT_SRC/en" ]; then
  rm -rf "$DICT_DST"
  mkdir -p "$DICT_DST"
  cp -r "$DICT_SRC"/. "$DICT_DST"/
  echo "dictionaries installed: $DICT_DST ($(find "$DICT_DST" -name '*.txt' | wc -l) files)"
else
  echo "WARNING: dictionaries not found at $DICT_SRC" >&2
fi

"$VENV_PY" - <<'PY'
from postal.expand import expand_address
out = expand_address("Main St")
assert "main street" in out, out
print("libpostal OK:", out)
PY

"$VENV_PY" - <<PY
import sys
sys.path.insert(0, "$HERE/error_taxonomy")
import analyze_error_types as m
root = m._dictionary_root()
assert root, "dictionaries not discoverable"
n = len(m._dictionary_expansions())
assert n > 1000, n
print(f"dictionaries OK: {n} abbreviations from {root}")
PY
