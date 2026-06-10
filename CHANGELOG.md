# Changelog

## [1.9.1] - 2026-06-10

### Fixed
- Skip silence no longer stops playback — `stop_periods=-1` prevents mpv from halting when silence is detected at end of audio segments
- Restored `lavfi=[...]` wrapper required by mpv for ffmpeg audio filters

## [1.9.0] - 2026-06-10

### Added
- **Login screen redesign** — full ASCII art header with `POCKET` in orange/red and `CLI` in matrix green
- **Blinking cursor** — `█` pulses at the end of `CLI` until the user presses any key
- **Rotating taglines** — one of five taglines shown randomly on each login
- **Login retry** — wrong password shows `Invalid credentials. Try again.` inline and re-prompts
- **"press any key" hint** — shown below separator during blink phase; disappears when email prompt appears

### Changed
- `import random` moved to top-level imports
- `curses_login` fully documented with docstring and section comments
- `endwin()` wrapped in try/except to prevent crash on login error

### Fixed
- First keypress during blink phase no longer consumed — printable chars prepended to email input
- Duplicate lazy `from datetime import datetime` removed

## [1.8.1] - 2026-06-10

### Fixed
- Files tab now uses natural sort (001, 002... DCC8, Drew, Fred)
- Natural sort applied in both `load_files` and `_load_last_played`

## [1.8.0] - 2026-06-09

### Added
- **Sleep timer** — press `z` for 5/15/30/60 min options; navigated with `↑↓` and `Enter`
- **Sleep countdown** — `Sleep: 14:32` right-justified in player bar
- **Cancel timer** — press `z` again to cancel from the same menu
- **Theme colors in lists** — items use theme `fg` and `info` colors throughout

### Changed
- Sleep timer pauses mpv and syncs position when it fires
- Discover list title and author respect theme colors

## [1.7.0] - 2026-06-06

### Added
- **Tab navigation** — `Tab`/`Shift+Tab` cycles focus between content, tab bar, sub-menu
- **Discover sub-menu** — `←` `→` between Trending/Popular/Featured; `Enter` loads list
- **Curated lists** — Trending, Popular, Featured from `lists.pocketcasts.com`
- **Delete file from cloud** — press `x` in Files tab
- **Smart delete confirmation** — single confirm for played, two-step for unplayed/in-progress

### Fixed
- Cursor scroll bug with player active (`player_h` mismatch)

## [1.6.1] - 2026-06-06

### Fixed
- Subscribe resolves real Pocket Casts UUID (fixes 400 Bad Request)

## [1.6.0] - 2026-06-06

### Added
- **Discover tab** — search and subscribe via iTunes
- **Subscribe/Unsubscribe** with confirmation

### Changed
- Background threads for all data loading
- 271 fewer lines overall

## [1.5.0] - 2026-06-05

### Added
- 20 built-in TOML themes, truecolor support, user themes

## [1.4.0] - 2026-06-05

### Added
- Theme selector, key badge UI

## [1.3.0] - 2026-06-05

### Added
- Keymap overlay, background threading

## [1.2.0] - 2026-06-05

### Added
- Chapters, episode descriptions, search, skip silence

## [1.0.0] - 2026-06-05

### Initial release
