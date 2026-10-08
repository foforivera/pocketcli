# Changelog

## [1.10.2] - 2026-10-08

### Fixed
- Episode progress never reached Pocket Casts: the position was posted to `/sync/update_episode_position`, which does not exist (HTTP 404, hidden until 1.10.0 started showing sync errors). Position and "played" now go to `/sync/update_episode` with the episode in the `uuid` field

## [1.10.1] - 2026-10-08

### Fixed
- Themes showed dark blue and dark green text in Konsole. Konsole reports that palette colors can be redefined but ignores the request, so the stock colors of slots 16-24 were shown. Konsole now gets the nearest color of the fixed 256-color palette
- Terminals with 256 colors but no palette redefinition now use the nearest 256-color match instead of the 8 basic ANSI colors

### Added
- `POCKETCLI_TRUECOLOR=1` or `=0` forces exact palette colors on or off

## [1.10.0] - 2026-10-08

### Added
- **Key registry**: one table now drives key handling, the `?` keymap, the footer and player hints and the README tables, so they cannot drift apart
- `pocketcli --keys`, `--version`, `--logout` and `--help`
- `Home` / `End` and `g` / `G` jump to the top or bottom of any list
- Theme, speed and skip silence are remembered between runs
- The keymap and theme overlays scroll, so they fit small terminals
- Sync failures are shown in the status bar (once per episode) instead of being dropped silently

### Changed
- Skip silence (`S`) applies immediately to what is playing
- Starting playback no longer freezes the UI while the stream URL is fetched; startup no longer waits for the "last played" lookup
- Resuming backs up 5 seconds; a position inside the first 15 seconds starts over
- `]` / `[` and `S` also work while nothing is playing (they set the value for the next play)
- The auth token file is written atomically with mode 0600; older files are tightened on start
- mpv uses one IPC socket per instance under `$XDG_RUNTIME_DIR` instead of a fixed path in `/tmp`

### Fixed
- Episodes opened from the Podcasts tab or from search synced under the RSS `guid`, which Pocket Casts does not know. They now use the real Pocket Casts episode UUID
- A stream that failed to start, or mpv dying mid-episode, marked the episode as played. Only playing to the end does now; otherwise the position is kept
- An mpv event arriving before a reply made the position read as 0:00, and pausing then synced position 0. Replies are matched by request id and the last good position is kept
- `q` quit the app while the keymap or theme overlay was open
- `q` could not be typed in the search boxes
- `Esc` took a full second to register
- The sleep timer resumed playback if it fired while already paused
- `d` on an empty list opened an invisible overlay that swallowed keys
- Two pocketcli instances fought over the same mpv socket
- Quitting with Ctrl-C skipped the final position sync
- An expired login now says so instead of a raw HTTP error
- A feed URL starting with `-` could be read by mpv as an option
- Looking up a feed by title could load another show's episodes; the result is now checked against the Pocket Casts episode list

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
