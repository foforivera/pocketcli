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
- **Tab navigation** — `Tab` moves focus between content, tab bar, and sub-menus; arrows navigate within each level
- **Discover tab** — browse Trending, Popular, and Featured lists; search and subscribe via iTunes
- **Subscribe / Unsubscribe** — manage your library without opening the app
- **Delete from cloud** — remove uploaded files from Pocket Casts cloud storage directly from the TUI
- **Bidirectional sync** — playback position synced to Pocket Casts every 30s and on exit
- **Resume on launch** — opens with the last played episode ready to go, press space to continue
- **Episode status** — ● played, ◐ in progress, ○ not played
- **Chapter support** — displays current chapter name, jump with `n` / `N`
- **Skip silence** — 3 levels (normal / medium / aggressive)
- **Speed control** — 0.5x to 2.0x without pitch change
- **Files support** — audiobooks and custom uploads with progress tracking
- **Episode descriptions** — press `d` to read the episode description with chapter breakdown
- **Search** — press `/` to search episodes or discover new podcasts via iTunes
- **20 built-in themes** — press `t` to switch; add your own TOML themes to `~/.config/pocketcli/themes/`
- **Truecolor support** — exact hex colors on compatible terminals, ANSI fallback otherwise
- **Keymap overlay** — press `?` to see all keybindings

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

You will be prompted for your Pocket Casts email and password. The auth token is saved to `~/.config/pocketcli/config.ini`. Your password is never stored.

---

## Navigation

| Key | Action |
|-----|--------|
| `Tab` | Move focus: content → tab bar → sub-menu |
| `Shift+Tab` | Move focus backwards |
| `←` `→` | Move between tabs or sub-menu items when focused |
| `Enter` | Select focused tab or item |
| `1` – `6` | Jump directly to tab |
| `↑` `↓` / `j` `k` | Navigate list |
| `PgUp` `PgDn` | Jump page |
| `Esc` | Back / close overlay / drop focus |
| `/` | Search episodes or discover podcasts |
| `d` | Show episode description and chapters |
| `u` | Unsubscribe from selected podcast |
| `x` | Delete selected file from cloud (Files tab) |
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

## Discover

The Discover tab (`6`) shows curated lists from Pocket Casts — no search required to get started.

- `Tab` to focus the sub-menu, then `←` `→` to switch between **Trending**, **Popular**, and **Featured**
- Press `/` to search by name or keyword via iTunes
- Press `Enter` on any result to subscribe; `✓` marks podcasts already in your library

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
- Episode listings are fetched from each podcast's RSS feed via the iTunes Search API.
- Spotify-exclusive podcasts do not have public RSS feeds and will not load episodes.
- Files (audiobooks) require a Pocket Casts Plus subscription.
- To log out: `rm ~/.config/pocketcli/config.ini`

---

## License

MIT
