# Changelog

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
