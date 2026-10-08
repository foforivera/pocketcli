# Changelog

## [1.11.1] - 2026-10-08

### Added
- **Up Next**: what you play becomes the current item of your Pocket Casts Up Next, so other devices follow along
- **Up Next tab** (`7`): the queue in order; `Enter` plays (episodes and uploaded files), `x` removes
- `a` / `A` add the selected episode to the end of Up Next or right after the current one
- **Key registry**: one table drives key handling, the `?` keymap, the on-screen hints and the README tables
- `Home` / `End` and `g` / `G` jump to the top or bottom of a list; `r` reloads it
- Theme, speed and skip silence are remembered between runs
- `pocketcli --keys`, `--version`, `--logout` and `--help`

### Changed
- Skip silence (`S`) applies right away to what is playing
- Starting playback and startup no longer freeze the UI
- Resuming backs up 5 seconds; a position inside the first 15 seconds starts over
- Sync failures are shown in the status bar instead of being dropped silently
- The keymap and theme overlays scroll, and the tab bar shortens itself, to fit small terminals
- The auth token file is written with mode 0600
- One mpv socket per instance under `$XDG_RUNTIME_DIR`, so two instances can run at once

### Fixed
- Episode progress did not reach Pocket Casts: it was posted to an endpoint that answers 404, and under the RSS `guid` instead of the Pocket Casts episode UUID
- A stream that failed to start, or mpv dying mid-episode, marked the episode as played
- The position could read as 0:00 and then be synced as 0 when pausing
- Themes showed dark blue and dark green text in Konsole
- `q` quit the app with the keymap or theme overlay open, and could not be typed in the search boxes
- `Esc` took a full second to register
- The sleep timer resumed playback if it fired while already paused
- Quitting with Ctrl-C skipped the final position sync
- An expired login now says so instead of showing a raw HTTP error

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
