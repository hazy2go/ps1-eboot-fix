# ps1-eboot-fix

Make PS1 `EBOOT.PBP` files work on a real PSP running **ARK-5** (and other modern CFW).

Two tools:

- **`fix_eboot.py`** repairs an EBOOT you already have, if it was made with popstation, popstation_md, PSX2PSP or another tool built on the same template.
- **`build_eboot.sh`** builds a working EBOOT from your own disc images (`.bin`), single- or multi-disc.

This repo contains no game data, firmware or Sony files. `build_eboot.sh` downloads the open-source tools it needs when it runs.

## Symptoms this fixes

| What you see | Cause | Fix |
|---|---|---|
| `The game could not be started (80020148)` | The EBOOT's `DATA.PSP` is an **encrypted** PSN one. ARK-5 stopped reading `KEYS.BIN` in July 2026, so it can't decrypt it. | Rebuild with a decrypted (plain ELF) `DATA.PSP`. `build_eboot.sh` does this. |
| Black screen after the PlayStation logo, logo flashes, or a freeze at the first movie | popstation-family tools write a **placeholder TOC** saying every disc ends at 27:19:22, and leave the disc size at 0. POPS thinks the disc ends early, so videos and streamed audio past that point fail. | `fix_eboot.py` writes the real length, counted from the EBOOT's own block index. |
| Game runs, but something specific misbehaves | Official PSN releases carry Sony's per-game POPS config. Home-made EBOOTs don't. | `--pop-fe-config` adds Sony's config for that disc ID, from the [pop-fe](https://github.com/sahlberg/pop-fe) database. |

The placeholder TOC is also fixed inside ARK-5 itself by [PSP-Arkfive/ARK-5#154](https://github.com/PSP-Arkfive/ARK-5/pull/154). Until that's merged and released, use this script.

## Repair an existing EBOOT

```sh
python3 fix_eboot.py --dry-run EBOOT.PBP        # show what would change
python3 fix_eboot.py --pop-fe-config EBOOT.PBP  # fix it, and add Sony's config if one exists
```

It edits the file in place and only touches the placeholder lead-out, a zero size field, and the config area. EBOOTs that are already correct are left alone, and running it twice is safe. It also tells you if `DATA.PSP` is encrypted. That part can't be patched in place, so rebuild with `build_eboot.sh`.

## Build from your own discs

Requirements: macOS or Linux, `git`, `make`, a C compiler, zlib, `curl`, `python3`.

```sh
./build_eboot.sh -t "Policenauts" -o out "Policenauts (Disc 1).bin" "Policenauts (Disc 2).bin"
```

- One `.bin` per disc, single-track MODE2/2352. For games with CD audio tracks, use pop-fe instead.
- Game IDs are read from each disc's `SYSTEM.CNF`.
- Optional `-a assets/` folder with `ICON0.PNG` (144×80), `PIC0.PNG` (310×180), `PIC1.PNG` (480×272) and `SND0.AT3` (ATRAC3, under about 500 KB) for the XMB icon, background and music. [atracdenc](https://github.com/dcherednik/atracdenc) makes the `.AT3`.
- Copy the output folder to `PSP/GAME/<anything>/EBOOT.PBP` on the memory stick.

Multi-disc EBOOTs swap discs from the PS-button menu.

## Example: Policenauts (English patch)

Tested on a PSP-3000 with 6.61 and ARK-5 (FasterARK + cIPL):

1. Apply the [Policenauts English patch](http://www.policenauts.net) to your own Japanese discs with xdelta. The result is two `.bin` files.
2. `./build_eboot.sh -t "Policenauts" -o Policenauts disc1.bin disc2.bin`
3. Copy `Policenauts/` to `PSP/GAME/`.

Before: `80020148`, then a black screen with Konami logo flashes once that was fixed. After: the intro and the game play, and disc 2 swaps from the PS menu.

## Side note: Wi-Fi on PSP-3000 with ARK

If a WPA2 router fails with "exchanging key information failed", make sure ARK's `wpa2` setting is **on** (`always, wpa2, on` in `SETTINGS.TXT`) and the connection uses **WPA-PSK (AES)**. With it off, the PSP sends an EAPOL-Start and never answers the router's WPA2 handshake. The PSP's own connection test may still end with an error at its final Sony-server step even when Wi-Fi works. Check with an app that uses the network instead.

## Credits

- [popstation / popstation_md](https://github.com/moparisthebest/popstation): the EBOOT packer (GPLv2)
- [PSXPackager](https://github.com/RupertAvery/PSXPackager): `BASE.PBP` template and decrypted `DATA.PSP`
- [pop-fe](https://github.com/sahlberg/pop-fe): per-game POPS configs and the TOC method
- [ARK-5](https://github.com/PSP-Arkfive/ARK-5): the CFW

## License

MIT. See `LICENSE`. The downloaded tools keep their own licenses.
