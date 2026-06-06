# Changelog

## [1.7.0] - 2026-06-06

### Added
- **Tab navigation** — `Tab` cycles focus between content, tab bar, and sub-menu (Discover); `Shift+Tab` goes backwards
- **Visual tab focus** — focused tab shows as reverse highlight, active tab stays green; clear distinction between "where you are" and "where the cursor is"
- **Discover sub-menu navigation** — when focus is on the Discover sub-menu, `←` `→` move between Trending / Popular / Featured; `Enter` loads the selected list
- **Curated lists in Discover** — Trending, Popular, and Featured load automatically from `lists.pocketcasts.com` when entering the Discover tab; no search needed to browse
- **Delete file from cloud** — press `x` on any file in the Files tab to delete it from Pocket Casts cloud storage
- **Smart delete confirmation** — played files (●) get a single confirm; unplayed or in-progress files (○ ◐) get a two-step confirm with progress shown

### Changed
- `TABS` and `DISCOVER_MODES` extracted as top-level constants — single source of truth for tab definitions
- `_activate_tab()` centralizes all tab-switching logic including data loading
- `_current_tab_idx()` derives the active tab index from app state instead of a separate variable
- `_close_discover_search()` eliminates duplicated close logic across `q`, `Esc`, and the key handler
- `from datetime import datetime` moved to top-level imports — no lazy imports inside methods
- Discover list visible rows calculated via `_visible_rows() - 2` instead of a hardcoded offset
- `f`, `p`, `e` keybinds removed from Discover — Tab navigation replaces them cleanly
- `_draw_badges_at(y, x, badges)` helper added for overlay badge rows at arbitrary positions

### Fixed
- Cursor scroll bug: `_visible_rows()` used `player_h=4` but `draw()` reserved `player_h=6`; cursor went invisible 2 rows before scroll triggered
- Discover key handler used hardcoded `h - 8` for visible rows; now uses `_visible_rows()` consistently

## [1.6.1] - 2026-06-06

### Fixed
- Subscribe now resolves the real Pocket Casts UUID from the feed URL before calling the API (fixes 400 Bad Request)
- Unsubscribe confirm overlay now uses key badges matching the rest of the UI
- Removed redundant `n` cancel key from unsubscribe confirm — only `y` to confirm, `Esc` to cancel

## [1.6.0] - 2026-06-06

### Added
- **Discover tab** (`6`) — search and subscribe to any podcast via iTunes directly from the TUI
- **Subscribe from Discover** — press `Enter` on a search result to subscribe; `✓` indicator shows already-subscribed podcasts
- **Unsubscribe with confirmation** — press `u` on any podcast in the Podcasts tab; confirm with `y` or cancel with `Esc`
- Podcast list reloads automatically after subscribing or unsubscribing

### Changed
- All data loading (queue, files) now runs in background threads — UI stays responsive
- `sync_episode` and `sync_file` are now separate API methods with cleaner names
- `_push_sync` helper eliminates duplicated sync logic across pause, periodic sync, and exit
- `SILENCE_FILTERS` moved to a top-level dict constant — cleaner MPV launch code
- All imports moved to top level (no more imports inside methods)
- `_itunes_search` extracted as shared API helper
- Separate `httpx.Client` for external API calls (no auth header conflicts)
- `_overlay_box` helper shared across all overlays
- `_draw_tabs` rewritten with a declarative list of tuples
- `load_queue` and `load_files` moved to background threads
- 271 fewer lines overall with no functionality removed

### Fixed
- `q` key now correctly closes discover input and unsub confirm before quitting
- `discover_searching` captured before global keys — no interference with `t`, `?`, `p`, `S`, etc.
- `_apply_theme` was called twice on init — now called once
- `_scroll` now handles `total == 0` without errors

## [1.5.0] - 2026-06-05

### Added
- TOML-based theme system with 20 built-in themes (Dracula, Nord, Tokyo Night, Catppuccin, Gruvbox, Rose Pine, and more)
- Truecolor support: themes use exact hex colors on supported terminals, ANSI fallback on others
- User themes: drop any `.toml` file in `~/.config/pocketcli/themes/` to add or override themes

## [1.4.7] - 2026-06-05

### Fixed
- File sync now uses correct endpoint (POST /files with array body)

## [1.4.6] - 2026-06-05

### Fixed
- File playback position now syncs correctly to Pocket Casts

## [1.4.5] - 2026-06-05

### Fixed
- Last played now correctly shows file when it was more recently played than a podcast episode

## [1.4.4] - 2026-06-05

### Fixed
- Last played prefers in_progress episode order when no timestamp available

## [1.4.3] - 2026-06-05

### Fixed
- Search input no longer interrupted by global keys (t, ?, d, 1-5, etc.)

## [1.4.2] - 2026-06-05

### Fixed
- Selection highlight and key badges now readable across all themes

## [1.4.1] - 2026-06-05

### Fixed
- Footer no longer duplicates nav badges when player is active

## [1.4.0] - 2026-06-05

### Added
- Theme selector with 10 themes (press t)
- Key badge UI for controls (CLIAMP-inspired)

## [1.3.3] - 2026-06-05

### Fixed
- Episode list shows "Loading..." while fetching instead of "No results."
- Race condition when switching podcasts quickly

## [1.3.0] - 2026-06-05

### Added
- Keymap overlay (press ?)
- Esc returns to podcast list from episode view

### Fixed
- Background threading - UI stays responsive while loading

## [1.2.0] - 2026-06-05

### Added
- Chapter display in player bar
- n / N to jump between chapters
- Episode description overlay with chapter separators (press d)
- Podcast and episode search (press /)
- Skip silence - 3 levels: normal, medium, aggressive (press S)

## [1.1.0] - 2026-06-05

### Fixed
- Podcast feed URL used directly to avoid wrong iTunes match
- Fallback to iTunes search when feed returns no episodes

## [1.0.0] - 2026-06-05

### Initial release
