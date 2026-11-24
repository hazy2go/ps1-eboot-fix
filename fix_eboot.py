#!/usr/bin/env python3
"""
fix_eboot.py - repair PS1 EBOOT.PBP files made by popstation-family tools
(popstation, popstation_md, PSX2PSP, and others built on the same template)
so they run on modern custom firmware such as ARK-5.

What it fixes, per disc:
  * TOC lead-out: these tools write a fixed placeholder (27:19:22). POPS then
    believes the disc ends early and anything past that point (FMV, XA audio)
    fails: black screen after the PlayStation logo, or a hang at the first
    video. The real length is counted from the EBOOT's own block index.
  * Disc size field (PSISOIMG+0x0C): often left at 0; filled in from the index.
  * Optional: Sony's per-game POPS config (as used by official PSN releases),
    written at PSISOIMG+0x420. Use --config FILE (one per disc, or one for all)
    or --pop-fe-config to fetch it from the pop-fe project by disc ID.

It also reports whether DATA.PSP is a plain ELF (works on ARK-5) or an
encrypted PSN one (fails with 80020148 on ARK-5, which no longer reads KEYS.BIN).

The file is modified in place. Run with --dry-run first to see what would change.
"""
import argparse
import re
import struct
import sys
import urllib.request

INDEX_OFFSET = 0x4000      # block index inside PSISOIMG
DATA_OFFSET = 0x100000     # compressed disc data inside PSISOIMG
BLOCK_SIZE = 0x9300        # one index block = 16 raw sectors of 2352 bytes
BLOCK_SECTORS = 16
PLACEHOLDER_LEADOUT = bytes([0x27, 0x19, 0x22])
POPFE_RAW = "https://raw.githubusercontent.com/sahlberg/pop-fe/master/"


def bcd(v):
    return ((v // 10) % 10) << 4 | (v % 10)


def unbcd(b):
    return (b >> 4) * 10 + (b & 0xF)


def count_blocks(f, psiso):
    """Count used entries in the PSISOIMG block index (32 bytes each)."""
    f.seek(psiso + INDEX_OFFSET)
    table = f.read(DATA_OFFSET - INDEX_OFFSET)
    count = 0
    for i in range(0, len(table) - 31, 32):
        length = struct.unpack_from("<I", table, i + 4)[0]
        if length == 0:
            break
        count += 1
    return count


def disc_offsets(f):
    f.seek(0)
    header = f.read(40)
    if header[:4] != b"\x00PBP":
        sys.exit("not a PBP file")
    offsets = struct.unpack("<8I", header[8:40])
    psar = offsets[7]
    f.seek(psar)
    magic = f.read(12)
    if magic.startswith(b"PSTITLEIMG"):
        f.seek(psar + 0x200)
        discs = [psar + p for p in struct.unpack("<5I", f.read(20)) if p]
    elif magic.startswith(b"PSISOIMG"):
        discs = [psar]
    else:
        sys.exit("no PSISOIMG/PSTITLEIMG found - not a PS1 EBOOT?")
    return offsets, discs


def disc_id(f, psiso):
    f.seek(psiso + 0x400)
    raw = f.read(11).decode("ascii", "replace")  # e.g. _SLPS_00215
    return raw.replace("_", "").strip("\x00")


def fetch_pop_fe_config(game_id):
    """Look up the PSP POPS config for a disc ID in pop-fe's game database."""
    db = urllib.request.urlopen(POPFE_RAW + "gamedb.py", timeout=30).read().decode("utf-8", "replace")
    m = re.search(r"'%s'\s*:\s*\{(.*?)\n\s*\}," % re.escape(game_id), db, re.S)
    if not m:
        return None
    p = re.search(r"'pspconfig'\s*:\s*\"([^\"]+)\"", m.group(1))
    if not p:
        return None
    path = urllib.request.quote(p.group(1))
    return urllib.request.urlopen(POPFE_RAW + path, timeout=30).read()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("eboot", help="EBOOT.PBP to repair (modified in place)")
    ap.add_argument("--config", action="append", default=[],
                    help="POPS config file to embed (repeat once per disc, or give one for all discs)")
    ap.add_argument("--pop-fe-config", action="store_true",
                    help="download each disc's Sony POPS config from the pop-fe project")
    ap.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    args = ap.parse_args()

    with open(args.eboot, "rb" if args.dry_run else "r+b") as f:
        offsets, discs = disc_offsets(f)

        f.seek(offsets[6])
        data_psp = f.read(4)
        if data_psp == b"\x7fELF":
            print("DATA.PSP: plain ELF (good for ARK-5)")
        else:
            print("DATA.PSP: encrypted %r - ARK-5 will refuse this with 80020148;" % data_psp)
            print("          rebuild with a decrypted DATA.PSP (see README)")

        configs = [open(c, "rb").read() for c in args.config]
        if configs and len(configs) not in (1, len(discs)):
            sys.exit("give one --config, or one per disc (%d discs)" % len(discs))

        for n, psiso in enumerate(discs, 1):
            f.seek(psiso)
            if f.read(12) != b"PSISOIMG0000":
                sys.exit("disc %d: PSISOIMG header missing" % n)
            gid = disc_id(f, psiso)
            blocks = count_blocks(f, psiso)
            if blocks == 0:
                sys.exit("disc %d: empty block index" % n)
            frames = blocks * BLOCK_SECTORS + 150  # 2 second pregap
            mm, ss, ff = frames // 4500, (frames // 75) % 60, frames % 75

            f.seek(psiso + 0x800)
            toc = bytearray(f.read(40))
            a2 = next((i for i in range(0, 40, 10) if toc[i + 2] == 0xA2), None)
            if a2 is None:
                sys.exit("disc %d: no lead-out (A2) entry in TOC" % n)
            old = toc[a2 + 7:a2 + 10]
            f.seek(psiso + 0x0C)
            old_size = struct.unpack("<I", f.read(4))[0]
            new_size = blocks * BLOCK_SIZE + DATA_OFFSET

            print("disc %d (%s): %d sectors" % (n, gid, blocks * BLOCK_SECTORS))
            changes = []
            if bytes(old) == PLACEHOLDER_LEADOUT:
                changes.append("lead-out %02d:%02d:%02d (placeholder) -> %02d:%02d:%02d"
                               % (unbcd(old[0]), unbcd(old[1]), unbcd(old[2]), mm, ss, ff))
                if not args.dry_run:
                    f.seek(psiso + 0x800 + a2 + 7)
                    f.write(bytes([bcd(mm), bcd(ss), bcd(ff)]))
            else:
                print("  lead-out %02d:%02d:%02d already set, left alone"
                      % (unbcd(old[0]), unbcd(old[1]), unbcd(old[2])))
            if old_size == 0:
                changes.append("disc size 0 -> 0x%X" % new_size)
                if not args.dry_run:
                    f.seek(psiso + 0x0C)
                    f.write(struct.pack("<I", new_size))

            cfg = None
            if configs:
                cfg = configs[0] if len(configs) == 1 else configs[n - 1]
            elif args.pop_fe_config:
                cfg = fetch_pop_fe_config(gid)
                if cfg is None:
                    print("  no pop-fe config for %s" % gid)
            if cfg:
                if len(cfg) > 0x3E0:
                    sys.exit("disc %d: config too large (%d bytes)" % (n, len(cfg)))
                changes.append("POPS config embedded (%d bytes)" % len(cfg))
                if not args.dry_run:
                    f.seek(psiso + 0x420)
                    f.write(cfg)

            for c in changes:
                print("  " + ("would: " if args.dry_run else "") + c)
            if not changes:
                print("  nothing to change")


if __name__ == "__main__":
    main()
