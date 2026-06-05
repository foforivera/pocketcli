# pocketcli

A terminal UI client for [Pocket Casts](https://pocketcasts.com). Browse your podcasts, episodes, and uploaded files (audiobooks) from the command line, with bidirectional sync back to the app.

Built with Python and `curses`. No Electron. No browser. Just a terminal.

---

## Features

- **Full TUI** — browse podcasts, episodes, queue, starred, and uploaded files
- **Bidirectional sync** — playback position synced to Pocket Casts every 30s and on exit
- **Resume on launch** — opens with the last played episode ready to go, press space to continue
- **Episode status** — ● played, ◐ in progress, ○ not played
- **Chapter support** — displays current chapter name, jump with `n` / `N`
- **Skip silence** — 3 levels (normal / medium / aggressive)
- **Speed control** — 0.5x to 2.0x without pitch change
- **Files support** — audiobooks and custom uploads with progress tracking
- **Episode descriptions** — press `d` to read the episode description with chapter breakdown
- **Search** — press `/` to search episodes or discover new podcasts via iTunes
- **Theme selector** — 10 built-in themes, press `t` to switch
- **Keymap overlay** — press `?` to see all keybindings
- **RSS-based listings** — full titles, durations, and dates pulled from podcast feeds

---

## Requirements

- Python 3.10+
- [mpv](https://mpv.io)
- A Pocket Casts account
- Pocket Casts Plus subscription required for Files / audiobooks

---

## Installation

### Linux (Arch / CachyOS / EndeavourOS / Manjaro)

```bash
git clone https://github.com/foforivera/pocketcli
cd pocketcli
bash install-linux.sh
```

### macOS

```bash
git clone https://github.com/foforivera/pocketcli
cd pocketcli
bash install-macos.sh
```

### Manual

```bash
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

You will be prompted for your Pocket Casts email and password. The auth token is saved locally to `~/.config/pocketcli/config.ini`. Your password is never stored.

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
| `Esc` / `Backspace` | Back to podcast list |
| `/` | Search episodes or discover podcasts |
| `d` | Show episode description and chapters |
| `t` | Theme selector |
| `?` | Keymap overlay |
| `q` | Quit (saves position) |

## Player controls

| Key | Action |
|-----|--------|
| `Space` / `p` | Play / Pause |
| `→` | +30 seconds |
| `←` | -30 seconds |
| `n` | Next chapter |
| `N` | Previous chapter |
| `]` | Speed up |
| `[` | Speed down |
| `S` | Cycle skip silence: off → normal → medium → aggressive |
| `q` | Quit (saves position) |

---

## Updating

```bash
# With the alias added by the installer:
pocketcli-update

# Or manually:
mv ~/Downloads/pocketcli.py ~/.local/bin/pocketcli && chmod +x ~/.local/bin/pocketcli
```

---

## Notes

- Uses the unofficial Pocket Casts API (reverse-engineered). Works well in practice but not officially supported.
- Episode listings are fetched from each podcast's RSS feed via the iTunes Search API.
- Spotify-exclusive podcasts do not have public RSS feeds and will not load episodes.
- Files (audiobooks) require a Pocket Casts Plus subscription.
- To log out: `rm ~/.config/pocketcli/config.ini`

---

## License

MIT
