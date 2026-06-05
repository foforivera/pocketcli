# pocketcli

A terminal UI client for [Pocket Casts](https://pocketcasts.com). Browse your podcasts, episodes, and uploaded files (audiobooks) from the command line, with bidirectional sync back to the app.

Built with Python and `curses`. No Electron. No browser. Just a terminal.

![pocketcli screenshot](https://i.imgur.com/placeholder.png)

---

## Features

- **Full TUI** — browse podcasts, episodes, queue, starred, and uploaded files
- **Bidirectional sync** — playback position synced to Pocket Casts every 30s and on exit
- **Resume on launch** — opens with the last played episode ready to go, press space to continue
- **Episode status** — ● played, ◐ in progress, ○ not played
- **Skip silence** — 3 levels (normal / medium / aggressive) using mpv's audio filter
- **Speed control** — 0.5x to 2.0x without pitch change
- **Files support** — audiobooks and custom uploads with progress tracking
- **Episode descriptions** — press `d` to read the episode description inline
- **RSS-based listings** — full titles, durations, and dates pulled from podcast feeds

---

## Requirements

- Python 3.10+
- [mpv](https://mpv.io)
- A Pocket Casts account (Plus subscription required for Files/audiobooks)

---

## Installation

### Linux (Arch / CachyOS / EndeavourOS / Manjaro)

```bash
git clone https://github.com/youruser/pocketcli
cd pocketcli
bash install-linux.sh
```

### macOS

```bash
git clone https://github.com/youruser/pocketcli
cd pocketcli
bash install-macos.sh
```

### Manual

```bash
# Install mpv and Python deps
# Linux (Arch): paru -S mpv python-httpx python-rich python-click
# macOS: brew install mpv && pip3 install httpx rich click

cp pocketcli.py ~/.local/bin/pocketcli
chmod +x ~/.local/bin/pocketcli
```

---

## First run

```bash
pocketcli
```

You'll be prompted for your Pocket Casts email and password. The auth token is saved locally to `~/.config/pocketcli/config.ini`. Your password is never stored.

---

## Navigation

| Key | Action |
|-----|--------|
| `1` | Podcasts |
| `2` | In Progress |
| `3` | New Episodes |
| `4` | Starred |
| `5` | Files / Audiobooks |
| `↑` `↓` / `j` `k` | Navigate list |
| `PgUp` `PgDn` | Jump page |
| `Enter` | Open podcast / play episode or file |
| `d` | Show episode description |
| `Esc` | Close description overlay |
| `Backspace` / `b` | Back to podcast list |
| `q` | Quit (saves position) |

## Player controls

| Key | Action |
|-----|--------|
| `Space` / `p` | Play / Pause |
| `→` | +30 seconds |
| `←` | -30 seconds |
| `]` | Speed up |
| `[` | Speed down |
| `S` | Cycle skip silence: off → normal → medium → aggressive |
| `q` | Quit (saves position) |

---

## Updating

If you downloaded a new `pocketcli.py`:

```bash
# With the pocketcli-update alias (added by the installer):
pocketcli-update

# Or manually:
mv ~/Downloads/pocketcli.py ~/.local/bin/pocketcli
chmod +x ~/.local/bin/pocketcli
```

---

## How sync works

1. On play, fetches the stream URL from the Pocket Casts API
2. Launches mpv with `--start=N` to resume from saved position
3. Every 30 seconds, POSTs current position to `api.pocketcasts.com`
4. On quit, saves final position
5. The mobile app sees the updated progress instantly

---

## Notes

- Uses the unofficial Pocket Casts API (reverse-engineered). Works well in practice but is not officially supported by Pocket Casts.
- Episode listings are fetched from the podcast's RSS feed via the iTunes Search API.
- Files (audiobooks) require a Pocket Casts Plus subscription.
- To log out: `rm ~/.config/pocketcli/config.ini`

---

## License

MIT
