#!/usr/bin/env bash
# Re-download WDC part_*.gz files that failed extraction (corrupted/incomplete gzip or bad content).
# Run this, then re-run extract_main; it will process only the files that still lack output.
# Usage: ./scripts/wget_failed_extraction.sh [WDC-ZIP root]
# Example: ./scripts/wget_failed_extraction.sh /pegasus/address-paper/WDC-ZIP

set -e
BASE_URL="https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12/quads/classspecific"
WGET_OPTS="--timeout=300 --tries=5 --user-agent=postalcrawl-wdc-downloader/1.0"
ROOT="${1:-/pegasus/address-paper/WDC-ZIP}"

# (subset, part_number) — from extraction errors in WDC-ZIP-extracted
FAILED="Hotel 2
GovernmentOrganization 1
LocalBusiness 79
GeoCoordinates 61
SportsEvent 5"

# wdc/GovernmentOrganization -> subset GovernmentOrganization, under wdc/
echo "$FAILED" | while read -r SUBSET PART; do
  [[ -z "$SUBSET" ]] && continue
  if [[ "$SUBSET" == "GovernmentOrganization" ]]; then
    OUT="$ROOT/wdc/$SUBSET/part_$PART.gz"
  else
    OUT="$ROOT/$SUBSET/part_$PART.gz"
  fi
  echo "Re-downloading $SUBSET part_$PART.gz -> $OUT"
  mkdir -p "$(dirname "$OUT")"
  wget $WGET_OPTS -O "$OUT" "$BASE_URL/$SUBSET/part_$PART.gz" || true
done
echo "Done. Re-run extraction; missing outputs will be generated."
