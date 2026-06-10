# Changelog

## [1.9.0] - 2026-06-10

### Added
- **Login screen redesign** — full ASCII art header with `POCKET` in orange/red and `CLI` in matrix green
- **Blinking cursor** — `█` pulses at the end of `CLI` until the user presses any key
- **Rotating taglines** — one of five taglines shown randomly on each login:
  - "the unofficial pocket casts terminal client."
  - "your pocket casts. your terminal."
  - "no browser. no electron. just audio."
  - "pocket casts... a bit different."
  - "pocket casts, without leaving the terminal."
- **Login retry** — wrong password shows `Invalid credentials. Try again.` inline and re-prompts without restarting the app
- **"press any key" hint** — shown below the separator during the blink phase; disappears cleanly when the email prompt appears

### Changed
- `import random` moved to top-level imports (was lazy inside `curses_login`)
- `curses_login` fully documented with docstring, section comments, and named layout variables
- `endwin()` wrapped in try/except to prevent crash on login error

### Fixed
- First keypress during blink phase no longer consumed silently — printable chars are correctly prepended to the email input
- Duplicate lazy `from datetime import datetime` inside `_load_last_played` removed

## [1.8.1] - 2026-06-10

### Fixed
- Files tab now uses natural sort (001, 002... DCC8, Drew, Fred) instead of lexicographic order
- Natural sort applied in both `load_files` and `_load_last_played` to cover both code paths

## [1.8.0] - 2026-06-09

### Added
- **Sleep timer** — press `z` to open a menu with 5 / 15 / 30 / 60 minute options; navigated with `↑↓` and `Enter`
- **Sleep countdown** — displays `Sleep: 14:32` right-justified in the player bar while timer is active
- **Cancel timer** — press `z` again while a timer is running to cancel it from the same menu
- **Theme colors in lists** — all list items now use the theme's `fg` color for text and `info` color for dates and durations

### Changed
- Sleep timer pauses mpv and syncs position when it fires — does not close the app
- List item text uses `color_pair(8)` (theme fg) instead of plain terminal white
- Right-side metadata uses `color_pair(3)` (theme info/yellow)
- Discover list title and author also respect theme colors

### Fixed
- VERSION bump now part of release checklist

## [1.7.0] - 2026-06-06

### Added
- **Tab navigation** — `Tab` cycles focus between content, tab bar, and sub-menu (Discover); `Shift+Tab` goes backwards
- **Visual tab focus** — focused tab shows as reverse highlight, active tab stays green
- **Discover sub-menu navigation** — `←` `→` move between Trending / Popular / Featured; `Enter` loads the selected list
- **Curated lists in Discover** — Trending, Popular, and Featured load automatically from `lists.pocketcasts.com`
- **Delete file from cloud** — press `x` on any file in the Files tab
- **Smart delete confirmation** — played files get single confirm; unplayed/in-progress get two-step confirm with progress shown

### Changed
- `TABS` and `DISCOVER_MODES` extracted as top-level constants
- `_activate_tab()` centralizes all tab-switching logic
- `_close_discover_search()` eliminates duplicated close logic
- `_draw_badges_at()` helper for overlay badge rows

### Fixed
- Cursor scroll bug: `_visible_rows()` used `player_h=4` but `draw()` reserved `player_h=6`
- Discover key handler used hardcoded `h - 8` for visible rows

## [1.6.1] - 2026-06-06

### Fixed
- Subscribe now resolves the real Pocket Casts UUID from the feed URL (fixes 400 Bad Request)
- Unsubscribe confirm overlay uses key badges matching the rest of the UI

## [1.6.0] - 2026-06-06

### Added
- **Discover tab** (`6`) — search and subscribe to any podcast via iTunes directly from the TUI
- **Subscribe from Discover** — `Enter` on a result subscribes; `✓` marks already-subscribed podcasts
- **Unsubscribe with confirmation** — press `u` on any podcast; confirm with `y` or cancel with `Esc`

### Changed
- All data loading runs in background threads
- `_push_sync` helper eliminates duplicated sync logic
- `SILENCE_FILTERS` moved to top-level dict constant
- `_overlay_box` helper shared across all overlays
- 271 fewer lines overall

### Fixed
- `q` correctly closes discover input and unsub confirm before quitting
- `_scroll` handles `total == 0` without errors

## [1.5.0] - 2026-06-05

### Added
- TOML-based theme system with 20 built-in themes
- Truecolor support with ANSI fallback
- User themes in `~/.config/pocketcli/themes/`

## [1.4.7] - 2026-06-05

### Fixed
- File sync now uses correct endpoint (POST /files with array body)

## [1.4.6] - 2026-06-05

### Fixed
- File playback position now syncs correctly to Pocket Casts

## [1.4.5] - 2026-06-05

### Fixed
- Last played correctly shows file when more recently played than a podcast episode

## [1.4.4] - 2026-06-05

### Fixed
- Last played prefers in_progress episode order when no timestamp available

## [1.4.3] - 2026-06-05

### Fixed
- Search input no longer interrupted by global keys

## [1.4.2] - 2026-06-05

### Fixed
- Selection highlight and key badges readable across all themes

## [1.4.1] - 2026-06-05

### Fixed
- Footer no longer duplicates nav badges when player is active

## [1.4.0] - 2026-06-05

### Added
- Theme selector with 10 themes (press t)
- Key badge UI for controls (CLIAMP-inspired)

## [1.3.3] - 2026-06-05

### Fixed
- Episode list shows "Loading..." while fetching
- Race condition when switching podcasts quickly

## [1.3.0] - 2026-06-05

### Added
- Keymap overlay (press ?)
- Esc returns to podcast list from episode view

### Fixed
- Background threading — UI stays responsive while loading

## [1.2.0] - 2026-06-05

### Added
- Chapter display in player bar
- n / N to jump between chapters
- Episode description overlay with chapter separators (press d)
- Podcast and episode search (press /)
- Skip silence — 3 levels

## [1.1.0] - 2026-06-05

### Fixed
- Podcast feed URL used directly to avoid wrong iTunes match
- Fallback to iTunes search when feed returns no episodes

## [1.0.0] - 2026-06-05

### Initial release
