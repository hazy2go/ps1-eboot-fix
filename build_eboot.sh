#!/usr/bin/env bash
# build_eboot.sh - build a PS1 EBOOT.PBP that runs on ARK-5 from your own disc images.
#
#   ./build_eboot.sh -t "Title" [-a assets_dir] [-o out_dir] disc1.bin [disc2.bin ...]
#
# Each .bin must be a single-track MODE2/2352 image (one .bin per disc).
# Multi-track games (CD audio) need merging first; use pop-fe for those.
#
# What it does:
#   1. builds popstation / popstation_md (github.com/moparisthebest/popstation)
#   2. fetches PSXPackager's BASE.PBP template and *decrypted* DATA.PSP
#      (github.com/RupertAvery/PSXPackager) - ARK-5 rejects encrypted ones
#   3. packs your discs (game IDs are read from each disc's SYSTEM.CNF)
#   4. runs fix_eboot.py: real TOC lead-out, disc size, Sony POPS config from pop-fe
#
# Optional: -a DIR with any of ICON0.PNG (144x80), PIC0.PNG (310x180),
# PIC1.PNG (480x272), SND0.AT3 (ATRAC3, < ~500 KB) for the XMB.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CACHE="${PS1_EBOOT_CACHE:-$HERE/.cache}"
TITLE=""
ASSETS=""
OUT="."
LEVEL=9

usage() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

while getopts "t:a:o:l:h" opt; do
  case "$opt" in
    t) TITLE="$OPTARG" ;;
    a) ASSETS="$OPTARG" ;;
    o) OUT="$OPTARG" ;;
    l) LEVEL="$OPTARG" ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
[ $# -ge 1 ] && [ $# -le 5 ] || usage
[ -n "$TITLE" ] || { echo "error: -t TITLE is required"; usage; }

for b in "$@"; do
  [ -f "$b" ] || { echo "error: $b not found"; exit 1; }
  [ $(( $(wc -c < "$b") % 2352 )) -eq 0 ] || { echo "error: $b is not a raw 2352-byte-sector image"; exit 1; }
done

# --- 1. popstation tools -----------------------------------------------------
mkdir -p "$CACHE"
if [ ! -x "$CACHE/popstation/popstation_md/popstation_md" ]; then
  echo ">> building popstation"
  rm -rf "$CACHE/popstation"
  git clone -q --depth 1 https://github.com/moparisthebest/popstation "$CACHE/popstation"
  make -s -C "$CACHE/popstation" >/dev/null
fi

# --- 2. BASE.PBP + decrypted DATA.PSP ----------------------------------------
RAW=https://raw.githubusercontent.com/RupertAvery/PSXPackager/master/Popstation/Resources
for f in BASE.PBP DATA.PSP; do
  [ -s "$CACHE/$f" ] || { echo ">> fetching $f"; curl -fsSL "$RAW/$f" -o "$CACHE/$f"; }
done
[ "$(head -c 4 "$CACHE/DATA.PSP" | xxd -p)" = "7f454c46" ] || { echo "error: DATA.PSP is not a plain ELF"; exit 1; }

# --- 3. pack -----------------------------------------------------------------
disc_id() {  # read the boot executable name from SYSTEM.CNF, e.g. SLPS_002.15 -> SLPS00215
  LC_ALL=C head -c 4000000 "$1" | LC_ALL=C grep -aoE 'cdrom:\\?[A-Z]{4}[_-][0-9]{3}\.[0-9]{2}' | head -1 \
    | sed -E 's/.*([A-Z]{4})[_-]([0-9]{3})\.([0-9]{2})/\1\2\3/'
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$CACHE/BASE.PBP" "$CACHE/DATA.PSP" "$WORK/"
if [ -n "$ASSETS" ]; then
  for f in ICON0.PNG PIC0.PNG PIC1.PNG SND0.AT3; do
    [ -f "$ASSETS/$f" ] && cp "$ASSETS/$f" "$WORK/" && echo ">> using $f"
  done
fi

IDS=(); BINS=()
for b in "$@"; do
  id="$(disc_id "$b")"
  [ -n "$id" ] || { echo "error: could not find a game ID in $b (no SYSTEM.CNF?)"; exit 1; }
  IDS+=("$id"); BINS+=("$(cd "$(dirname "$b")" && pwd)/$(basename "$b")")
  echo ">> $(basename "$b"): $id"
done

cd "$WORK"
if [ $# -eq 1 ]; then
  "$CACHE/popstation/popstation/popstation" "$TITLE" "${IDS[0]}" "$LEVEL" "${BINS[0]}" >/dev/null
else
  TITLES=(); LEVELS=()
  for i in "${!BINS[@]}"; do TITLES+=("$TITLE - Disc $((i + 1))"); LEVELS+=("$LEVEL"); done
  "$CACHE/popstation/popstation_md/popstation_md" "$TITLE" "${TITLES[@]}" "${IDS[0]}" "${IDS[@]}" "${LEVELS[@]}" "${BINS[@]}" >/dev/null
fi
cd - >/dev/null

# --- 4. fix ------------------------------------------------------------------
python3 "$HERE/fix_eboot.py" --pop-fe-config "$WORK/EBOOT.PBP"

mkdir -p "$OUT"
mv "$WORK/EBOOT.PBP" "$OUT/EBOOT.PBP"
echo ">> done: $OUT/EBOOT.PBP  (copy its folder to PSP/GAME/ on the memory stick)"
