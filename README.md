# pocketcli

A terminal UI client for [Pocket Casts](https://pocketcasts.com). Browse your podcasts, episodes, and uploaded files (audiobooks) from the command line, with bidirectional sync back to the app.

> Because sometimes you just want to listen to podcasts without opening a browser, a PWA, an Electron app, and accidentally 47 Chrome tabs.

Built with Python and `curses`. No Electron. No browser. Just a terminal.

---

## Inspired by CLIAMP

[CLIAMP](https://github.com/bjarneo/cliamp) is a terminal music player that proved you can have a great listening experience without sacrificing your RAM to the browser gods. Same philosophy here: less visual noise, more focus, and your computer actually stays cool.

---

## Features

- **Full TUI** — browse podcasts, episodes, queue, starred, and uploaded files
- **Up Next**: what you play becomes the current item of your Pocket Casts Up Next, so the phone app follows along; a tab shows the queue, `a` / `A` add episodes, `x` removes
- **Tab navigation** — `Tab` moves focus between content, tab bar, and sub-menus; arrows navigate within each level
- **Discover tab** — browse Trending, Popular, and Featured lists; search and subscribe via iTunes
- **Subscribe / Unsubscribe** — manage your library without opening the app
- **Delete from cloud** — remove uploaded files from Pocket Casts cloud storage directly from the TUI
- **Sleep timer** — set a 5, 15, 30, or 60 minute timer; pauses playback and syncs position when it fires
- **Bidirectional sync** — playback position synced to Pocket Casts every 30s, on pause and on exit; a failed sync is shown instead of being dropped silently
- **Resume on launch** — opens with the last played episode ready to go, press space to continue; resuming backs up 5 seconds for context
- **Episode status** — ● played, ◐ in progress, ○ not played
- **Chapter support** — displays current chapter name, jump with `n` / `N`
- **Skip silence** — 3 levels (normal / medium / aggressive), applied right away while playing
- **Speed control** — 0.5x to 2.0x without pitch change
- **Remembers your settings**: theme, speed and skip silence are kept between runs
- **Files support** — audiobooks and custom uploads with progress tracking
- **Episode descriptions** — press `d` to read the episode description with chapter breakdown
- **Search** — press `/` to search episodes or discover new podcasts via iTunes
- **20 built-in themes** — press `t` to switch; list items use the theme's colors throughout
- **Truecolor support** — exact hex colors on compatible terminals, ANSI fallback otherwise
- **Keymap overlay** — press `?` to see all keybindings (scrolls on small terminals)

---

## Requirements

- Python 3.10+
- [mpv](https://mpv.io)
- A Pocket Casts account
- Pocket Casts Plus subscription required for Files / audiobooks

---

## Installation

### Arch Linux / CachyOS / EndeavourOS / Manjaro (AUR)

```bash
paru -S pocketcli
```

### Arch Linux (manual)

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

### Manual (any system)

```bash
# Arch: paru -S mpv python-httpx
# macOS: brew install mpv && pip3 install httpx

cp pocketcli.py ~/.local/bin/pocketcli
chmod +x ~/.local/bin/pocketcli
```

---

## First run

```bash
pocketcli
```

You will be prompted for your Pocket Casts email and password. The auth token is saved to `~/.config/pocketcli/config.ini`, readable only by you. Your password is never stored.

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

The Discover tab (`6`) shows curated lists from Pocket Casts — no search required to get started.

- `Tab` to focus the sub-menu, then `←` `→` to switch between **Trending**, **Popular**, and **Featured**
- Press `/` to search by name or keyword via iTunes
- Press `Enter` on any result to subscribe; `✓` marks podcasts already in your library

---

## Sleep Timer

Press `z` while playing to open the sleep timer menu. Navigate with `↑↓` and confirm with `Enter`. The countdown shows as `Sleep: 14:32` on the right side of the player bar. Press `z` again to cancel.

---

## Themes

20 built-in themes: ayu-mirage-dark, catppuccin, catppuccin-latte, dracula, ember, ethereal, everforest, flexoki-light, gruvbox, hackerman, kanagawa, matte-black, miasma, neon-blade-runner, nord, osaka-jade, ristretto, rose-pine, tokyo-night, vantablack.

To add a custom theme, create a `.toml` file in `~/.config/pocketcli/themes/`:

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

# Manual (with the alias added by the installer)
pocketcli-update
```

---

## Notes

- Uses the unofficial Pocket Casts API (reverse-engineered). Works well in practice but not officially supported.
- Episode listings are fetched from each podcast's RSS feed via the iTunes Search API, then matched against the Pocket Casts episode list so progress syncs under the right episode. An episode Pocket Casts does not list yet still plays, with a note that its progress will not sync.
- An episode is marked as played only when it plays to the end. If the stream fails, the position is kept and space resumes it.
- Spotify-exclusive podcasts do not have public RSS feeds and will not load episodes.
- Files (audiobooks) require a Pocket Casts Plus subscription.
- To log out: `pocketcli --logout`

---

## License

MIT
