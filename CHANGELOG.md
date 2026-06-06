# Changelog

## [1.6.0] - 2026-06-06

### Added
- **Discover tab** (`6`) — search and subscribe to any podcast via iTunes directly from the TUI
- **Subscribe from Discover** — press `Enter` on a search result to subscribe; `✓` indicator shows already-subscribed podcasts
- **Unsubscribe with confirmation** — press `u` on any podcast in the Podcasts tab; confirm with `y` or cancel with `n` / `Esc`
- Podcast list reloads automatically after subscribing or unsubscribing

### Changed
- All data loading (queue, files) now runs in background threads — UI stays responsive
- `sync_episode` and `sync_file` are now separate API methods with cleaner names
- `_push_sync` helper in TUI eliminates duplicated sync logic across pause, periodic sync, and exit
- `SILENCE_FILTERS` moved to a top-level dict constant — cleaner MPV launch code
- All imports moved to top level (no more imports inside methods)
- `_itunes_search` extracted as shared API helper used by search and episode fetching
- Separate `httpx.Client` instance for external API calls (no auth header conflicts)
- `_overlay_box` helper shared across all overlays (theme, keymap, desc, unsub confirm)
- `_draw_tabs` rewritten with a declarative list of tuples
- `load_queue` and `load_files` moved to background threads
- Tab 1 now correctly stays active when in episode view
- `_scroll` now handles `total == 0` without errors
- 271 fewer lines overall with no functionality removed

### Fixed
- `q` key now correctly closes discover input mode and unsub confirm before quitting
- `discover_searching` input now captured before global keys (`t`, `?`, `p`, `S`, etc.) — no interference
- `_apply_theme` was called twice on init — now called once

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
