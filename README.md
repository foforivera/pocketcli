<div align="center">

# pocketcli

**Pocket Casts in your terminal.**

Browse your podcasts, play episodes and audiobooks, and keep your progress in sync with the Pocket Casts app on your phone.

![Linux](https://img.shields.io/badge/Linux-supported-2ea44f?logo=linux&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-supported-2ea44f?logo=apple&logoColor=white)
[![AUR](https://img.shields.io/aur/version/pocketcli?logo=archlinux&label=AUR)](https://aur.archlinux.org/packages/pocketcli)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

[Install](#installation) · [First run](#first-run) · [Keys](#keys) · [Themes](#themes) · [Notes](#notes)

</div>

> Because sometimes you just want to listen to podcasts without opening a browser, a PWA, an Electron app, and accidentally 47 Chrome tabs.

Built with Python and `curses`, with [mpv](https://mpv.io) doing the playback. No Electron. No browser. Just a terminal.

---

## Quick start

```bash
# Arch / CachyOS / EndeavourOS / Manjaro
paru -S pocketcli

# macOS (needs Homebrew)
git clone https://github.com/foforivera/pocketcli && cd pocketcli && bash install-macos.sh

# then
pocketcli
```

Log in with your Pocket Casts email and password the first time, and you are in.

---

## Does it run on my system?

| System | Status | How |
|--------|--------|-----|
| Arch and friends | ✅ Yes | AUR package or `install-linux.sh` |
| macOS | ✅ Yes | `install-macos.sh` (Homebrew) |
| Other Linux (Debian, Ubuntu, Fedora...) | ✅ Yes | [Manual install](#manual-any-linux-or-macos) |
| Windows | ⚠️ Through WSL | Run it inside WSL. Native Windows has no `curses`, and the mpv control socket works differently there |

---

## Features

**Listening**
- **Bidirectional sync**: playback position goes back to Pocket Casts every 30s, on pause and on exit. A failed sync is shown instead of dropped silently
- **Up Next**: what you play becomes the current item of your Pocket Casts Up Next, so the phone app follows along. A tab shows the queue, `a` / `A` add episodes, `x` removes
- **Resume on launch**: opens with the last played episode ready to go, press space to continue. Resuming backs up 5 seconds for context
- **Speed control**: 0.5x to 3.0x without pitch change
- **Skip silence**: 3 levels (normal / medium / aggressive), applied right away while playing
- **Chapters**: shows the current chapter name, jump with `n` / `N`
- **Sleep timer**: 5, 15, 30 or 60 minutes. Pauses playback and syncs position when it fires
- **Files support**: audiobooks and custom uploads with progress tracking (Pocket Casts Plus)

**Browsing**
- **Full TUI**: podcasts, episodes, in progress, new, starred, files, discover and Up Next, each in its own tab
- **Discover tab**: Trending, Popular and Featured lists, plus search and subscribe via iTunes
- **Search**: press `/` to search episode titles and descriptions, or find new podcasts
- **Episode status**: ● played, ◐ in progress, ○ not played
- **Episode descriptions**: press `d` to read the description with chapter breakdown
- **Manage your library**: subscribe, unsubscribe and delete uploaded files without opening the app

**Looks and comfort**
- **20 built-in themes**: press `t` to switch, or add your own
- **Truecolor support**: exact hex colors on compatible terminals, ANSI fallback otherwise
- **Remembers your settings**: theme, speed and skip silence are kept between runs
- **Keymap overlay**: press `?` to see every key (scrolls on small terminals)

---

## Requirements

- Python 3.10+ and the `httpx` package
- [mpv](https://mpv.io)
- A Pocket Casts account
- Pocket Casts Plus, only if you want Files / audiobooks

---

## Installation

### Arch Linux / CachyOS / EndeavourOS / Manjaro (AUR)

```bash
paru -S pocketcli      # or: yay -S pocketcli
```

### Arch Linux (from the repo)

```bash
git clone https://github.com/foforivera/pocketcli 2>/dev/null || git -C pocketcli pull
cd pocketcli
bash install-linux.sh
```

### macOS

You need [Homebrew](https://brew.sh). The installer adds mpv, a recent Python if yours is too old, and `httpx`.

```bash
git clone https://github.com/foforivera/pocketcli 2>/dev/null || git -C pocketcli pull
cd pocketcli
bash install-macos.sh
```

It installs to `~/.local/bin` and adds that folder to your PATH for zsh, bash and fish. Open a new terminal afterwards.

### Manual (any Linux or macOS)

Install the dependencies:

```bash
# Arch
sudo pacman -S mpv python-httpx
# Debian / Ubuntu
sudo apt install mpv python3-httpx
# Fedora
sudo dnf install mpv python3-httpx
# macOS
brew install mpv python && pip3 install httpx
```

Then copy the script:

```bash
mkdir -p ~/.local/bin
cp pocketcli.py ~/.local/bin/pocketcli
chmod +x ~/.local/bin/pocketcli
```

Make sure `~/.local/bin` is in your PATH.

---

## First run

```bash
pocketcli
```

You will be asked for your Pocket Casts email and password. The auth token is saved to `~/.config/pocketcli/config.ini`, readable only by you. Your password is never stored.

Other options:

```bash
pocketcli --version   # print the version
pocketcli --keys      # print the keymap as Markdown
pocketcli --logout    # forget the saved login
```

---

## Keys

Press `?` inside the app for this list. The tables below are generated with `pocketcli --keys`, so they always match what the app does.

### Navigation

| Key | Action |
|-----|--------|
| `Tab` | Focus: content, tab bar, sub-menu |
| `Shift+Tab` | Focus: reverse direction |
| `← →` | Move between tabs or sub-menu items when focused |
| `1-7` | Jump directly to tab |
| `↑↓ / j k` | Navigate list |
| `PgUp PgDn` | Jump page |
| `Home End / g G` | Jump to top / bottom |
| `Enter` | Open, play or subscribe to the selected item |
| `Esc` | Back / close overlay / drop focus |
| `Backspace / b` | Back to the podcast list (episode list) |
| `/` | Search episodes or discover podcasts |
| `d` | Show episode description and chapters |
| `u` | Unsubscribe from selected podcast (Podcasts tab) |
| `x` | Delete selected file from cloud (Files tab) |
| `a / A` | Add to Up Next: at the end / right after the current one |
| `x` | Remove from Up Next (Up Next tab) |
| `r` | Reload the current list |

### Player

| Key | Action |
|-----|--------|
| `Space / p` | Play / Pause |
| `← →` | Seek -30 / +30 seconds |
| `n / N` | Next / previous chapter |
| `] / [` | Speed up / down |
| `S` | Skip silence: off / normal / medium / aggressive |
| `z` | Sleep timer (5 / 15 / 30 / 60 min) |

### Other

| Key | Action |
|-----|--------|
| `t` | Theme selector |
| `?` | Keymap overlay |
| `q` | Quit (saves position) |

---

## Discover

The Discover tab (`6`) shows curated lists from Pocket Casts, no search needed to get started.

- `Tab` to focus the sub-menu, then `←` `→` to switch between **Trending**, **Popular** and **Featured**
- Press `/` to search by name or keyword via iTunes
- Press `Enter` on any result to subscribe. `✓` marks podcasts already in your library

---

## Sleep timer

Press `z` while playing to open the sleep timer menu. Move with `↑↓` and confirm with `Enter`. The countdown shows as `Sleep: 14:32` on the right side of the player bar. Press `z` again to cancel.

---

## Themes

20 built-in themes: ayu-mirage-dark, catppuccin, catppuccin-latte, dracula, ember, ethereal, everforest, flexoki-light, gruvbox, hackerman, kanagawa, matte-black, miasma, neon-blade-runner, nord, osaka-jade, ristretto, rose-pine, tokyo-night, vantablack.

To add your own, create a `.toml` file in `~/.config/pocketcli/themes/`:

```toml
accent    = "#89b4fa"
bright_fg = "#cdd6f4"
fg        = "#9399b2"
green     = "#a6e3a1"
yellow    = "#f9e2af"
red       = "#f38ba8"
```

User themes override built-ins with the same name.

---

## Updating

```bash
# AUR
paru -Syu pocketcli

# From the repo (Arch or macOS)
cd pocketcli && git pull && bash install-linux.sh   # or install-macos.sh

# Manual, with the alias added by the installer
pocketcli-update
```

---

## Notes

- Uses the unofficial Pocket Casts API (reverse-engineered). Works well in practice, but it is not officially supported.
- Episode listings come from each podcast's RSS feed via the iTunes Search API, then get matched against the Pocket Casts episode list so progress syncs under the right episode. An episode Pocket Casts does not list yet still plays, with a note that its progress will not sync.
- An episode is marked as played only when it plays to the end. If the stream fails, the position is kept and space resumes it.
- Spotify-exclusive podcasts have no public RSS feed and will not load episodes.
- Files (audiobooks) require Pocket Casts Plus.

---

## Inspired by CLIAMP

[CLIAMP](https://github.com/bjarneo/cliamp) is a terminal music player that proved you can have a great listening experience without sacrificing your RAM to the browser gods. Same philosophy here: less visual noise, more focus, and your computer actually stays cool.

---

## License

[MIT](LICENSE)
