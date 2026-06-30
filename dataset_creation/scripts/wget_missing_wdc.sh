#!/usr/bin/env bash
# Download missing WDC part_*.gz files (e.g. after timeouts) using wget.
# Usage: ./scripts/wget_missing_wdc.sh [WDC-ZIP root]
# Example: ./scripts/wget_missing_wdc.sh /pegasus/address-paper/WDC-ZIP

set -e
BASE_URL="https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12/quads/classspecific"
WGET_OPTS="--timeout=300 --tries=5 --user-agent=postalcrawl-wdc-downloader/1.0"
ROOT="${1:-/pegasus/address-paper/WDC-ZIP}"

# LocalBusiness: missing part_131 through part_140 (10 files)
SUBSET="LocalBusiness"
for i in 131 132 133 134 135 136 137 138 139 140; do
  OUT="$ROOT/$SUBSET/part_$i.gz"
  if [[ -f "$OUT" ]]; then
    echo "Skip (exists): $OUT"
    continue
  fi
  mkdir -p "$(dirname "$OUT")"
  echo "Downloading $SUBSET part_$i.gz ..."
  wget $WGET_OPTS -O "$OUT" "$BASE_URL/$SUBSET/part_$i.gz" || true
done
echo "Done."
