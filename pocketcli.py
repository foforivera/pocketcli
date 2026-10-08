#!/usr/bin/env python3
"""
pocketcli - Terminal client for Pocket Casts
Browse podcasts, play episodes, sync progress bidirectionally.
"""

VERSION = "1.11.1"
BUILD   = "2026-10-08"

import os
import re
import sys
import json
import time
import socket
import curses
import tempfile
import subprocess
import configparser
import threading
import random
import urllib.parse
import urllib.request
from datetime import datetime
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

CONFIG_DIR  = Path.home() / ".config" / "pocketcli"
CONFIG_FILE = CONFIG_DIR / "config.ini"
THEMES_DIR  = CONFIG_DIR / "themes"
BASE_URL    = "https://api.pocketcasts.com"
CACHE_URL   = "https://podcast-api.pocketcasts.com"
ITUNES_URL  = "https://itunes.apple.com/search"
LISTS_URL   = "https://lists.pocketcasts.com"
USER_AGENT  = f"pocketcli/{VERSION}"

# Pocket Casts files things under this fixed "podcast" id when an uploaded
# file (audiobook) sits in Up Next
FILE_PODCAST_UUID = "da7aba5e-f11e-f11e-f11e-da7aba5ef11e"

# Resume rules. A position inside the first RESUME_MIN seconds is not worth
# resuming, a resumed episode backs up RESUME_REWIND seconds for context, and
# an episode stopped inside its last PLAYED_TAIL seconds counts as played.
RESUME_MIN    = 15
RESUME_REWIND = 5
PLAYED_TAIL   = 60


def _runtime_dir():
    """Directory for the mpv IPC socket: private to the user when possible."""
    d = os.environ.get("XDG_RUNTIME_DIR")
    if d and os.path.isdir(d) and os.access(d, os.W_OK):
        return d
    return tempfile.gettempdir()

# Tab definitions: (key, label, view, queue_mode)
TABS = [
    ("1", "Podcasts",    "podcasts",  None),
    ("2", "In Progress", "queue",     "in_progress"),
    ("3", "New",         "queue",     "new"),
    ("4", "Starred",     "queue",     "starred"),
    ("5", "Files",       "files",     None),
    ("6", "Discover",    "discover",  None),
    ("7", "Up Next",     "queue",     "up_next"),
]

# Discover sub-modes
DISCOVER_MODES = [
    ("trending", "Trending"),
    ("popular",  "Popular"),
    ("featured", "Featured"),
]

SPEEDS      = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]

SILENCE_FILTERS = {
    0: None,
    # lavfi wrapper required for ffmpeg filters in mpv
    # stop_periods=-1 prevents mpv from stopping at detected silence at end of file
    1: "lavfi=[silenceremove=start_periods=1:start_silence=0.5:start_threshold=-40dB:stop_periods=-1:stop_silence=0.5:stop_threshold=-40dB]",
    2: "lavfi=[silenceremove=start_periods=1:start_silence=0.3:start_threshold=-35dB:stop_periods=-1:stop_silence=0.3:stop_threshold=-35dB]",
    3: "lavfi=[silenceremove=start_periods=1:start_silence=0.15:start_threshold=-30dB:stop_periods=-1:stop_silence=0.15:stop_threshold=-30dB]",
}

# ─────────────────────────────────────────────
# Key registry
# ─────────────────────────────────────────────
#
# One table describes every key: what it does, where it applies and how it is
# shown. The dispatcher, the keymap overlay (?), the footer and player badges
# and `pocketcli --keys` (the README tables) all read it, so they cannot drift
# apart. To add a key: add a row here and an _act_<name> method on PocketTUI.

SEC_NAV    = "Navigation"
SEC_PLAYER = "Player"
SEC_OTHER  = "Other"


def _bind(keys, action, arg=None):
    """keys: characters or curses key codes that trigger PocketTUI._act_<action>(arg)."""
    return (tuple(ord(k) if isinstance(k, str) else k for k in keys), action, arg)


class KeyRow:
    """One line of the keymap.

    section      heading it is listed under
    label, desc  how the key and its action read in the keymap overlay
    binds        list of _bind(); empty for keys handled by the input loop itself
    views        views where the key is active (None = everywhere); the Up Next
                 tab counts as its own view, "upnext" (see PocketTUI._ctx)
    needs        "mpv" when the key only works while something is playing
    badge        short text for the footer hint row (None = not shown there)
    badge_views  views whose footer shows the badge (default: same as views)
    pbadge       short text for the player hint row (None = not shown there)
    blabel       short key label for badges (default: label)
    help         False for rows that only exist to feed a badge
    """
    __slots__ = ("section", "label", "desc", "binds", "views", "needs",
                 "badge", "badge_views", "pbadge", "blabel", "help")

    def __init__(self, section, label, desc, binds=(), views=None, needs=None,
                 badge=None, badge_views=None, pbadge=None, blabel=None, help=True):
        self.section     = section
        self.label       = label
        self.desc        = desc
        self.binds       = list(binds)
        self.views       = views
        self.needs       = needs
        self.badge       = badge
        self.badge_views = badge_views if badge_views is not None else views
        self.pbadge      = pbadge
        self.blabel      = blabel or label
        self.help        = help


_ENTER = (curses.KEY_ENTER, 10, 13)

KEYMAP = [
    # ── Navigation ──
    KeyRow(SEC_NAV, "Tab",       "Focus: content, tab bar, sub-menu"),
    KeyRow(SEC_NAV, "Shift+Tab", "Focus: reverse direction"),
    KeyRow(SEC_NAV, "← →",       "Move between tabs or sub-menu items when focused"),
    KeyRow(SEC_NAV, f"1-{len(TABS)}", "Jump directly to tab",
           binds=[_bind([key], "tab", i) for i, (key, _, _, _) in enumerate(TABS)]),
    KeyRow(SEC_NAV, "↑↓ / j k",  "Navigate list",
           binds=[_bind([curses.KEY_DOWN, "j"], "move", 1), _bind([curses.KEY_UP, "k"], "move", -1)],
           badge="navigate", blabel="↑↓"),
    KeyRow(SEC_NAV, "PgUp PgDn", "Jump page",
           binds=[_bind([curses.KEY_NPAGE], "page", 1), _bind([curses.KEY_PPAGE], "page", -1)]),
    KeyRow(SEC_NAV, "Home End / g G", "Jump to top / bottom",
           binds=[_bind([curses.KEY_HOME, "g"], "edge", -1), _bind([curses.KEY_END, "G"], "edge", 1)]),
    KeyRow(SEC_NAV, "Enter",     "Open, play or subscribe to the selected item",
           binds=[_bind(_ENTER, "select")]),
    KeyRow(SEC_NAV, "Enter", "", views=("podcasts",),                  badge="open",      help=False),
    KeyRow(SEC_NAV, "Enter", "", views=("episodes", "queue", "upnext", "files"), badge="play", help=False),
    KeyRow(SEC_NAV, "Enter", "", views=("discover",),                  badge="subscribe", help=False),
    KeyRow(SEC_NAV, "Esc",       "Back / close overlay / drop focus"),
    KeyRow(SEC_NAV, "Esc",   "", views=("episodes",),                  badge="back",      help=False),
    KeyRow(SEC_NAV, "Backspace / b", "Back to the podcast list (episode list)",
           binds=[_bind([curses.KEY_BACKSPACE, 127, "b"], "back")], views=("episodes",)),
    KeyRow(SEC_NAV, "/",         "Search episodes or discover podcasts",
           binds=[_bind(["/"], "search")], views=("podcasts", "episodes", "discover"), badge="search"),
    KeyRow(SEC_NAV, "d",         "Show episode description and chapters",
           binds=[_bind(["d"], "describe")], views=("episodes", "queue"), badge="desc"),
    KeyRow(SEC_NAV, "u",         "Unsubscribe from selected podcast (Podcasts tab)",
           binds=[_bind(["u"], "unsubscribe")], views=("podcasts",), badge="unsub"),
    KeyRow(SEC_NAV, "x",         "Delete selected file from cloud (Files tab)",
           binds=[_bind(["x"], "delete_file")], views=("files",), badge="delete"),
    KeyRow(SEC_NAV, "a / A",     "Add to Up Next: at the end / right after the current one",
           binds=[_bind(["a"], "queue_add", "last"), _bind(["A"], "queue_add", "next")],
           views=("episodes", "queue"), badge="up next", blabel="a/A"),
    KeyRow(SEC_NAV, "x",         "Remove from Up Next (Up Next tab)",
           binds=[_bind(["x"], "queue_remove")], views=("upnext",), badge="remove"),
    KeyRow(SEC_NAV, "r",         "Reload the current list",
           binds=[_bind(["r"], "reload")], views=("podcasts", "queue", "upnext", "files")),

    # ── Player ──
    KeyRow(SEC_PLAYER, "Space / p", "Play / Pause",
           binds=[_bind([" ", "p"], "toggle_play")], pbadge="pause", blabel="Spc"),
    KeyRow(SEC_PLAYER, "← →",    "Seek -30 / +30 seconds",
           binds=[_bind([curses.KEY_RIGHT], "seek", 30), _bind([curses.KEY_LEFT], "seek", -30)],
           needs="mpv", pbadge="±30s", blabel="←→"),
    KeyRow(SEC_PLAYER, "n / N",  "Next / previous chapter",
           binds=[_bind(["n"], "chapter", 1), _bind(["N"], "chapter", -1)],
           needs="mpv", pbadge="chapter", blabel="n/N"),
    KeyRow(SEC_PLAYER, "] / [",  "Speed up / down",
           binds=[_bind(["]"], "speed", 1), _bind(["["], "speed", -1)], pbadge="speed", blabel="] ["),
    KeyRow(SEC_PLAYER, "S",      "Skip silence: off / normal / medium / aggressive",
           binds=[_bind(["S"], "cycle_silence")], pbadge="silence"),
    KeyRow(SEC_PLAYER, "z",      "Sleep timer (5 / 15 / 30 / 60 min)",
           binds=[_bind(["z"], "sleep_menu")], pbadge="sleep"),

    # ── Other ──
    KeyRow(SEC_OTHER, "t",       "Theme selector",
           binds=[_bind(["t"], "themes")], badge="theme", badge_views=("podcasts",), pbadge="theme"),
    KeyRow(SEC_OTHER, "?",       "Keymap overlay",
           binds=[_bind(["?"], "keys")], badge="keys", pbadge="keys"),
    KeyRow(SEC_OTHER, "q",       "Quit (saves position)", badge="quit", pbadge="quit"),
]


def keymap_markdown():
    """The keymap as Markdown tables, one per section (used for the README)."""
    out = []
    for section in (SEC_NAV, SEC_PLAYER, SEC_OTHER):
        out += [f"## {section}", "", "| Key | Action |", "|-----|--------|"]
        out += [f"| `{r.label}` | {r.desc} |" for r in KEYMAP if r.help and r.section == section]
        out.append("")
    return "\n".join(out)


class Overlay:
    """An overlay or text-entry mode that takes over the keyboard while open.

    is_open(tui)  whether it is showing
    close         PocketTUI method that dismisses it (Esc, and q unless text)
    key           PocketTUI method that receives every other key
    draw          PocketTUI method that paints it (None when drawn inline)
    text          True when it has a text field, so q types a letter
    """
    __slots__ = ("name", "is_open", "close", "key", "draw", "text")

    def __init__(self, name, is_open, close, key, draw=None, text=False):
        self.name, self.is_open, self.close = name, is_open, close
        self.key, self.draw, self.text = key, draw, text


# Top first. The first open overlay gets the keys; drawing goes bottom-up so
# that same overlay is also the one painted on top.
OVERLAYS = [
    Overlay("delete",   lambda t: t.del_file_step > 0, "_close_delete",   "_key_delete",   "_draw_delete_file_overlay"),
    Overlay("unsub",    lambda t: t.unsub_confirm,     "_close_unsub",    "_key_unsub",    "_draw_unsub_confirm_overlay"),
    Overlay("sleep",    lambda t: t.show_sleep_menu,   "_close_sleep",    "_key_sleep",    "_draw_sleep_menu_overlay"),
    Overlay("keys",     lambda t: t.show_keys,         "_close_keys",     "_key_keys",     "_draw_keymap_overlay"),
    Overlay("themes",   lambda t: t.show_themes,       "_close_themes",   "_key_themes",   "_draw_theme_overlay"),
    Overlay("search",   lambda t: t.searching,         "_close_search",   "_handle_search_key", "_draw_search_overlay", text=True),
    Overlay("discover", lambda t: t.discover_searching, "_close_discover_search", "_handle_discover_key", None, text=True),
    Overlay("desc",     lambda t: t.show_desc,         "_close_desc",     "_key_desc",     "_draw_desc_overlay"),
]

# ─────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────

def _read_config():
    cfg = configparser.ConfigParser()
    try:
        if CONFIG_FILE.exists():
            cfg.read(CONFIG_FILE)
    except Exception:
        pass
    return cfg


def _write_config(cfg):
    """Write config.ini atomically with mode 0600: it holds the auth token."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
    fd  = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        os.fchmod(f.fileno(), 0o600)   # also when a stale temp file was reused
        cfg.write(f)
    os.replace(tmp, CONFIG_FILE)


def load_token():
    if not CONFIG_FILE.exists():
        return None
    try:
        # Files written by older versions were world-readable
        if CONFIG_FILE.stat().st_mode & 0o077:
            os.chmod(CONFIG_FILE, 0o600)
    except Exception:
        pass
    return _read_config().get("auth", "token", fallback=None)


def save_config(email, token, uuid):
    cfg = _read_config()
    cfg["auth"] = {"email": email, "token": token, "uuid": uuid}
    _write_config(cfg)


def load_prefs():
    """Return saved UI preferences: theme name, speed index, skip silence level."""
    cfg = _read_config()
    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, cfg.getint("ui", key, fallback=default)))
        except Exception:
            return default
    return {
        "theme":        cfg.get("ui", "theme", fallback=""),
        "speed_idx":    _int("speed_idx", 2, 0, len(SPEEDS) - 1),
        "skip_silence": _int("skip_silence", 0, 0, 3),
    }


def save_prefs(theme, speed_idx, skip_silence):
    try:
        cfg = _read_config()
        if not cfg.has_section("auth"):
            return  # logged out while running: do not recreate the file
        cfg["ui"] = {
            "theme":        theme,
            "speed_idx":    str(speed_idx),
            "skip_silence": str(skip_silence),
        }
        _write_config(cfg)
    except Exception:
        pass


def resume_start(saved, status=0):
    """Where to start playback given a saved position, in seconds."""
    # The feed duration is not used to decide "already finished" here: feeds
    # often understate it (inserted ads), which would restart a long episode.
    saved = int(saved or 0)
    if status == 3 or saved < RESUME_MIN:
        return 0
    return saved - RESUME_REWIND


def is_played(item):
    """True when a list item (episode or file) shows as played."""
    dur  = int(item.get("duration", 0) or 0)
    pos  = int(item.get("playedUpTo", 0) or 0)
    stat = int(item.get("playingStatus", 0) or 0)
    return stat == 3 or bool(dur and pos >= dur - 30)


def is_finished(pos, duration):
    """True when a position is close enough to the end to count as played."""
    pos, duration = float(pos or 0), float(duration or 0)
    if duration <= 0:
        return False
    return pos >= duration - min(PLAYED_TAIL, duration / 2)


# ─────────────────────────────────────────────
# Theme system
# ─────────────────────────────────────────────

BUILTIN_THEMES = [
    ("ayu-mirage-dark",   "accent=#73d0ff\nbright_fg=#f3f4f5\nfg=#cccac2\ngreen=#d5ff80\nyellow=#ffad66\nred=#f28779"),
    ("catppuccin",        "accent=#89b4fa\nbright_fg=#cdd6f4\nfg=#9399b2\ngreen=#a6e3a1\nyellow=#f9e2af\nred=#f38ba8"),
    ("catppuccin-latte",  "accent=#1e66f5\nbright_fg=#4c4f69\nfg=#8c8fa1\ngreen=#40a02b\nyellow=#df8e1d\nred=#d20f39"),
    ("dracula",           "accent=#bd93f9\nbright_fg=#f8f8f2\nfg=#6272a4\ngreen=#50fa7b\nyellow=#f1fa8c\nred=#ff5555"),
    ("ember",             "accent=#e07040\nbright_fg=#e8d0b8\nfg=#907868\ngreen=#a08858\nyellow=#d8a050\nred=#c04848"),
    ("ethereal",          "accent=#7d82d9\nbright_fg=#ffcead\nfg=#9a96a8\ngreen=#92a593\nyellow=#E9BB4F\nred=#ED5B5A"),
    ("everforest",        "accent=#7fbbb3\nbright_fg=#d3c6aa\nfg=#7a8478\ngreen=#a7c080\nyellow=#dbbc7f\nred=#e67e80"),
    ("flexoki-light",     "accent=#205EA6\nbright_fg=#100F0F\nfg=#6F6E69\ngreen=#879A39\nyellow=#D0A215\nred=#D14D41"),
    ("gruvbox",           "accent=#7daea3\nbright_fg=#d4be98\nfg=#a89984\ngreen=#a9b665\nyellow=#d8a657\nred=#ea6962"),
    ("hackerman",         "accent=#82FB9C\nbright_fg=#ddf7ff\nfg=#8e95b8\ngreen=#4fe88f\nyellow=#50f7d4\nred=#50f872"),
    ("kanagawa",          "accent=#7e9cd8\nbright_fg=#dcd7ba\nfg=#938aa9\ngreen=#76946a\nyellow=#c0a36e\nred=#c34043"),
    ("matte-black",       "accent=#e68e0d\nbright_fg=#bebebe\nfg=#777777\ngreen=#FFC107\nyellow=#b91c1c\nred=#D35F5F"),
    ("miasma",            "accent=#78824b\nbright_fg=#c2c2b0\nfg=#666666\ngreen=#5f875f\nyellow=#b36d43\nred=#685742"),
    ("neon-blade-runner", "accent=#e8609a\nbright_fg=#b8c4d0\nfg=#758494\ngreen=#4eb8a8\nyellow=#d4a040\nred=#c85070"),
    ("nord",              "accent=#81a1c1\nbright_fg=#d8dee9\nfg=#8690a0\ngreen=#a3be8c\nyellow=#ebcb8b\nred=#bf616a"),
    ("osaka-jade",        "accent=#509475\nbright_fg=#F7E8B2\nfg=#C1C497\ngreen=#549e6a\nyellow=#459451\nred=#FF5345"),
    ("ristretto",         "accent=#f38d70\nbright_fg=#e6d9db\nfg=#948a8b\ngreen=#adda78\nyellow=#f9cc6c\nred=#fd6883"),
    ("rose-pine",         "accent=#56949f\nbright_fg=#575279\nfg=#908caa\ngreen=#286983\nyellow=#ea9d34\nred=#b4637a"),
    ("tokyo-night",       "accent=#7aa2f7\nbright_fg=#cfc9c2\nfg=#737aa2\ngreen=#9ece6a\nyellow=#e0af68\nred=#f7768e"),
    ("vantablack",        "accent=#8d8d8d\nbright_fg=#ffffff\nfg=#8d8d8d\ngreen=#b6b6b6\nyellow=#cecece\nred=#a4a4a4"),
]


def _parse_theme_toml(name, text):
    t = {"name": name, "accent": "", "bright_fg": "", "fg": "",
         "green": "", "yellow": "", "red": ""}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        if key in t:
            t[key] = val
    return t


def _hex_to_curses_color(hex_color, color_id):
    """Register a truecolor value in curses. Returns True on success."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return False
    try:
        r = int(h[0:2], 16) * 1000 // 255
        g = int(h[2:4], 16) * 1000 // 255
        b = int(h[4:6], 16) * 1000 // 255
        curses.init_color(color_id, r, g, b)
        return True
    except Exception:
        return False


_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


def _hex_to_256(hex_color):
    """Return the nearest color of the fixed xterm 256-color palette.
    Needs no palette change, so it works on every 256-color terminal."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return curses.COLOR_WHITE
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return curses.COLOR_WHITE

    def nearest(v):
        return min(range(6), key=lambda i: abs(_CUBE_LEVELS[i] - v))

    ri, gi, bi = nearest(r), nearest(g), nearest(b)
    cube      = 16 + 36 * ri + 6 * gi + bi
    cube_dist = ((r - _CUBE_LEVELS[ri]) ** 2 + (g - _CUBE_LEVELS[gi]) ** 2
                 + (b - _CUBE_LEVELS[bi]) ** 2)
    # Grayscale ramp: 232..255 are 8, 18, ... 238
    gray_i    = max(0, min(23, round(((r + g + b) / 3 - 8) / 10)))
    gray_v    = 8 + 10 * gray_i
    gray_dist = (r - gray_v) ** 2 + (g - gray_v) ** 2 + (b - gray_v) ** 2
    return 232 + gray_i if gray_dist < cube_dist else cube


def _can_redefine_colors():
    """Whether exact theme colors can be set by redefining palette entries.

    curses only reports what terminfo claims. Konsole advertises the ability
    (as xterm-256color) but ignores the request, which left themes showing the
    stock dark blues and greens of palette slots 16-24. POCKETCLI_TRUECOLOR=1
    or =0 overrides the guess for other terminals."""
    forced = os.environ.get("POCKETCLI_TRUECOLOR", "").strip().lower()
    if forced in ("0", "no", "off", "false"):
        return False
    if not (curses.can_change_color() and curses.COLORS >= 256):
        return False
    if forced in ("1", "yes", "on", "true"):
        return True
    return "KONSOLE_VERSION" not in os.environ


def _hex_to_ansi(hex_color):
    """Return the nearest ANSI curses color to a hex value."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return curses.COLOR_WHITE
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    ansi = [
        (curses.COLOR_BLACK,    0,   0,   0),
        (curses.COLOR_RED,    170,   0,   0),
        (curses.COLOR_GREEN,    0, 170,   0),
        (curses.COLOR_YELLOW, 170, 170,   0),
        (curses.COLOR_BLUE,     0,   0, 170),
        (curses.COLOR_MAGENTA, 170,  0, 170),
        (curses.COLOR_CYAN,     0, 170, 170),
        (curses.COLOR_WHITE,  170, 170, 170),
    ]
    best, best_dist = curses.COLOR_WHITE, float("inf")
    for color, cr, cg, cb in ansi:
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < best_dist:
            best_dist, best = dist, color
    return best


def _load_themes():
    """Load builtin themes + user themes from ~/.config/pocketcli/themes/.
    User themes override builtins with the same name."""
    themes = {}
    for name, text in BUILTIN_THEMES:
        themes[name] = _parse_theme_toml(name, text)
    if THEMES_DIR.exists():
        for f in sorted(THEMES_DIR.glob("*.toml")):
            try:
                themes[f.stem] = _parse_theme_toml(f.stem, f.read_text())
            except Exception:
                pass
    return sorted(themes.values(), key=lambda t: t["name"].lower())


# ─────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────

def fmt_dur(secs):
    if not secs:
        return "--:--"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_date(iso):
    return iso[:10] if iso else ""


def trunc(text, n):
    if not text:
        return ""
    return text if len(text) <= n else text[:n - 1] + "…"


# ─────────────────────────────────────────────
# API
# ─────────────────────────────────────────────

class AuthExpired(Exception):
    """The saved token was rejected by Pocket Casts."""

    def __str__(self):
        return "Session expired. Run 'pocketcli --logout' and log in again."


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _norm_title(text):
    return re.sub(r"\s+", " ", (text or "")).strip().casefold()


def _unique_by_title(items):
    """Map normalized title -> item, leaving out titles that repeat.
    A title shared by two episodes identifies neither of them."""
    seen, dupes = {}, set()
    for it in items:
        key = _norm_title(it.get("title"))
        if not key:
            continue
        if key in seen:
            dupes.add(key)
        seen[key] = it
    return {k: v for k, v in seen.items() if k not in dupes}


class API:
    def __init__(self, token):
        self.token  = token
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
                "User-Agent":    USER_AGENT,
            },
            timeout=15,
        )
        # Separate client for external APIs (no auth headers)
        self._ext = httpx.Client(
            timeout=10, follow_redirects=True, headers={"User-Agent": USER_AGENT},
        )

    # ── Internal helpers ──

    @staticmethod
    def _check(r):
        if r.status_code == 401:
            raise AuthExpired()
        r.raise_for_status()
        return r

    def _post(self, path, data=None):
        return self._check(self.client.post(f"{BASE_URL}{path}", json=data or {})).json()

    def _get(self, path):
        return self._check(self.client.get(f"{BASE_URL}{path}")).json()

    def _itunes_search(self, term, entity="podcast", limit=15):
        """Search iTunes catalog. Returns raw results list."""
        url = f"{ITUNES_URL}?term={urllib.parse.quote(term)}&entity={entity}&limit={limit}"
        return self._ext.get(url).json().get("results", [])

    # ── Podcast list & episodes ──

    def subscribed_podcasts(self):
        return self._post("/user/podcast/list", {"v": 1}).get("podcasts", [])

    def resolve_podcast_uuid(self, feed_url):
        """Resolve a Pocket Casts UUID from a feed URL."""
        try:
            r = self.client.post(
                f"{BASE_URL}/discover/search",
                json={"term": feed_url},
            )
            if r.status_code == 200:
                podcasts = r.json().get("podcasts", [])
                if podcasts:
                    return podcasts[0].get("uuid")
        except Exception:
            pass
        return None

    def subscribe_podcast(self, podcast_uuid):
        return self._post("/user/podcast/subscribe", {"uuid": podcast_uuid})

    def unsubscribe_podcast(self, podcast_uuid):
        return self._post("/user/podcast/unsubscribe", {"uuid": podcast_uuid})

    def podcast_feed_url(self, podcast_title):
        """Look up RSS feed URL for a podcast title via iTunes."""
        try:
            results = self._itunes_search(podcast_title, limit=5)
            want    = _norm_title(podcast_title)
            exact   = [r for r in results if _norm_title(r.get("collectionName")) == want]
            if exact or results:
                return (exact or results)[0].get("feedUrl")
        except Exception:
            pass
        return None

    def podcast_episodes_from_rss(self, feed_url, sync_data=None):
        """Parse an RSS feed and return episode dicts, merged with sync data."""
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_data = resp.read()

            root    = ET.fromstring(xml_data)
            ns      = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
            channel = root.find("channel")
            if channel is None:
                return []

            sync     = sync_data or {}
            episodes = []

            for item in channel.findall("item"):
                title  = item.findtext("title", "").strip()
                guid   = item.findtext("guid", "").strip()
                pub    = item.findtext("pubDate", "")
                url_el = item.find("enclosure")
                url    = url_el.get("url", "") if url_el is not None else ""

                # Duration from itunes:duration tag
                dur_str  = item.findtext("itunes:duration", "", ns).strip()
                duration = 0
                if dur_str:
                    parts = dur_str.split(":")
                    try:
                        if len(parts) == 3:
                            duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        elif len(parts) == 2:
                            duration = int(parts[0]) * 60 + int(parts[1])
                        else:
                            duration = int(parts[0])
                    except Exception:
                        pass

                # Pub date to ISO
                pub_iso = ""
                if pub:
                    try:
                        pub_iso = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
                    except Exception:
                        pub_iso = pub[:10]

                # Description - strip HTML
                desc_raw = (
                    item.findtext("itunes:summary", "", ns) or
                    item.findtext("description", "") or ""
                ).strip()
                desc = re.sub(r"<[^>]+>", "", desc_raw).strip()

                ep = {
                    "title":         title,
                    "uuid":          guid,
                    "url":           url,
                    "duration":      duration,
                    "publishedAt":   pub_iso,
                    "description":   desc,
                    "playedUpTo":    sync.get(guid, {}).get("playedUpTo", 0),
                    "playingStatus": sync.get(guid, {}).get("playingStatus", 0),
                }
                episodes.append(ep)

            return episodes
        except Exception:
            return []

    def podcast_cache_episodes(self, podcast_uuid):
        """Episode list from the public Pocket Casts cache, with real UUIDs."""
        r = self._ext.get(f"{CACHE_URL}/podcast/full/{podcast_uuid}")
        r.raise_for_status()
        return (r.json().get("podcast") or {}).get("episodes") or []

    @staticmethod
    def attach_real_uuids(episodes, cache_eps):
        """Give RSS episodes their Pocket Casts UUID.

        An RSS item only carries the publisher's guid, and Pocket Casts does
        not know an episode by that, so syncing with it does nothing. Match by
        audio URL first, then by a title that is unique on both sides. The
        guid is kept under "guid". Episodes left unmatched are flagged
        "unresolved" so the player can say their progress will not sync."""
        by_url   = {c.get("url"): c for c in cache_eps if c.get("url")}
        by_title = _unique_by_title(cache_eps)
        own      = _unique_by_title(episodes)
        for ep in episodes:
            match = by_url.get(ep.get("url"))
            if not match:
                key = _norm_title(ep.get("title"))
                if own.get(key) is ep:
                    match = by_title.get(key)
            ep["guid"] = ep.get("uuid", "")
            if match and match.get("uuid"):
                ep["uuid"] = match["uuid"]
                if match.get("published"):
                    ep["published"] = match["published"]   # full timestamp, for Up Next
                if not ep.get("duration"):
                    ep["duration"] = int(match.get("duration") or 0)
                ep.pop("unresolved", None)
            else:
                ep["unresolved"] = True
        return episodes

    def user_episode_states(self, podcast_uuid):
        """Per-episode sync state for one podcast, keyed by episode UUID."""
        eps = self._post("/user/podcast/episodes", {"uuid": podcast_uuid}).get("episodes", [])
        return {e.get("uuid"): e for e in eps if e.get("uuid")}

    def podcast_episodes(self, podcast_uuid, podcast_title="", feed_url=None):
        """Fetch episodes via RSS (for descriptions) and the Pocket Casts cache
        (for real UUIDs), then merge in the listening state."""
        try:
            cache_eps = self.podcast_cache_episodes(podcast_uuid)
        except Exception:
            cache_eps = []

        episodes = self.podcast_episodes_from_rss(feed_url) if feed_url else []
        if not episodes and podcast_title:
            # The stored URL is often the show's website, not its feed
            looked_up = self.podcast_feed_url(podcast_title)
            if looked_up and looked_up != feed_url:
                feed_url = looked_up
                episodes = self.podcast_episodes_from_rss(feed_url)

        if episodes and cache_eps:
            self.attach_real_uuids(episodes, cache_eps)
            if all(ep.get("unresolved") for ep in episodes):
                # Nothing lines up: the title lookup found another show's feed
                episodes = []

        if not episodes:
            if cache_eps:
                # No usable feed: the cache alone is enough to list and play
                episodes = [{
                    "title":         c.get("title", ""),
                    "uuid":          c.get("uuid", ""),
                    "url":           c.get("url", ""),
                    "duration":      int(c.get("duration") or 0),
                    "publishedAt":   (c.get("published") or "")[:10],
                    "published":     c.get("published") or "",
                    "description":   "",
                    "playedUpTo":    0,
                    "playingStatus": 0,
                } for c in cache_eps]
            elif not feed_url:
                return self._post("/user/podcast/episodes", {
                    "uuid": podcast_uuid, "page": 0, "sort": 3,
                }).get("episodes", [])
            else:
                return []

        self.merge_states(podcast_uuid, episodes)
        return episodes

    def merge_states(self, podcast_uuid, episodes):
        """Copy playedUpTo / playingStatus onto episodes, by UUID when we have
        it and by unique title otherwise."""
        def _apply(ep, src):
            ep["playedUpTo"]    = src.get("playedUpTo", 0) or 0
            ep["playingStatus"] = src.get("playingStatus", 0) or 0

        try:
            states = self.user_episode_states(podcast_uuid)
            for ep in episodes:
                if ep.get("uuid") in states:
                    _apply(ep, states[ep["uuid"]])
        except AuthExpired:
            raise
        except Exception:
            pass

        try:
            # Only this podcast's items: titles like "Episode 1" repeat across shows
            in_prog  = [e for e in self.in_progress()
                        if (e.get("podcastUuid") or e.get("podcast_uuid")
                            or e.get("podcast") or podcast_uuid) == podcast_uuid]
            by_uuid  = {e.get("uuid"): e for e in in_prog if e.get("uuid")}
            by_title = _unique_by_title(in_prog)
            own      = _unique_by_title(episodes)
            for ep in episodes:
                match = by_uuid.get(ep.get("uuid"))
                if not match:
                    key = _norm_title(ep.get("title"))
                    if own.get(key) is ep:
                        match = by_title.get(key)
                if match:
                    _apply(ep, match)
        except AuthExpired:
            raise
        except Exception:
            pass

    # ── Queue endpoints ──

    def in_progress(self):
        return self._post("/user/in_progress").get("episodes", [])

    def new_releases(self):
        return self._post("/user/new_releases").get("episodes", [])

    def starred(self):
        return self._post("/user/starred").get("episodes", [])

    # ── Up Next ──

    @staticmethod
    def up_next_episode(pod_uuid, ep, url=None):
        """The episode object the Up Next calls expect, or None.

        The server stores whatever it is sent: an episode with an empty uuid
        is accepted and then breaks reading the queue. So nothing incomplete
        is ever sent, and both ids must look like Pocket Casts UUIDs."""
        if ep.get("unresolved"):
            return None
        published = ep.get("published") or ep.get("publishedAt") or ""
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
            published += "T00:00:00Z"
        payload = {
            "uuid":      ep.get("uuid"),
            "title":     ep.get("title"),
            "url":       ep.get("url") or ep.get("streamUrl") or url,
            "podcast":   pod_uuid,
            "published": published,
        }
        if not all(isinstance(v, str) and v.strip() for v in payload.values()):
            return None
        if not (_UUID_RE.fullmatch(payload["uuid"]) and _UUID_RE.fullmatch(payload["podcast"])):
            return None
        return payload

    def up_next_list(self):
        """The Up Next queue in order, first item = what is current."""
        try:
            data = self._post("/up_next/list",
                              {"version": 2, "model": "webplayer", "showPlayStatus": True})
        except httpx.HTTPStatusError:
            # The play-status variant fails if the queue holds a broken entry
            data = self._post("/up_next/list", {"version": 2})
        eps = data.get("episodes") or []
        return [e for e in eps if isinstance(e, dict) and e.get("uuid")]

    def up_next_add(self, where, payload):
        """where: "now" (make current), "next" or "last". Returns None or an error."""
        if where not in ("now", "next", "last") or not payload:
            return "nothing to add"
        try:
            self._post(f"/up_next/play_{where}", {"version": 2, "episode": payload})
        except Exception as e:
            return self._err(e)
        return None

    def up_next_remove(self, uuids):
        uuids = [u for u in uuids if isinstance(u, str) and _UUID_RE.fullmatch(u)]
        if not uuids:
            return "nothing to remove"
        try:
            self._post("/up_next/remove", {"version": 2, "uuids": uuids})
        except Exception as e:
            return self._err(e)
        return None

    # ── Curated lists ──

    def curated_list(self, mode):
        r = self._ext.get(f"{LISTS_URL}/{mode}.json")
        r.raise_for_status()
        return r.json().get("podcasts", [])

    # ── Search ──

    def search_podcasts(self, query):
        """Search podcasts via iTunes. Returns normalized list of dicts."""
        try:
            return [
                {
                    "uuid":       str(p.get("collectionId", "")),
                    "title":      p.get("collectionName", ""),
                    "author":     p.get("artistName", ""),
                    "feedUrl":    p.get("feedUrl", ""),
                    "artworkUrl": p.get("artworkUrl60", ""),
                }
                for p in self._itunes_search(query)
            ]
        except Exception:
            return []

    # ── Files / audiobooks ──

    def files(self):
        return self._get("/files?include_bookmarks=true").get("files", [])

    def file_stream_url(self, file_uuid):
        return self._get(f"/files/play/{file_uuid}").get("url")

    # ── Episode streaming ──

    def episode_stream_url(self, podcast_uuid, episode_uuid):
        try:
            r = self.client.get(
                f"{BASE_URL}/podcasts/episode/stream/url",
                params={"podcast": podcast_uuid, "episode": episode_uuid},
            )
            if r.status_code == 200:
                return r.json().get("url")
        except Exception:
            pass
        # Fallback: direct episode endpoint
        try:
            ep = self.client.get(
                f"{BASE_URL}/podcasts/episode",
                params={"podcast": podcast_uuid, "episode": episode_uuid},
            )
            if ep.status_code == 200:
                return ep.json().get("url") or ep.json().get("streamUrl")
        except Exception:
            pass
        return None

    # ── Sync ──

    # The sync calls return None on success or a short error message. They
    # never raise: a failed sync must not interrupt playback, but the caller
    # shows the message instead of losing progress silently.

    @staticmethod
    def _err(e):
        if isinstance(e, httpx.HTTPStatusError):
            return f"HTTP {e.response.status_code}"
        return str(e) or e.__class__.__name__

    def sync_episode(self, podcast_uuid, episode_uuid, position_secs):
        """Push playback position to Pocket Casts.

        The endpoint is /sync/update_episode and the episode goes in "uuid".
        (/sync/update_episode_position does not exist: it answered 404, which
        older versions swallowed, so episode progress never reached the server.)"""
        try:
            self._post("/sync/update_episode", {
                "uuid":     episode_uuid,
                "podcast":  podcast_uuid,
                "position": int(position_secs),
                "status":   2,
            })
        except Exception as e:
            return self._err(e)
        return None

    def sync_file(self, file_uuid, position_secs, status=2):
        """Push file playback position to Pocket Casts."""
        try:
            self._post("/files", {"files": [{
                "uuid":          file_uuid,
                "playedUpTo":    int(position_secs),
                "playingStatus": status,
            }]})
        except Exception as e:
            return self._err(e)
        return None

    def delete_file(self, file_uuid):
        """Delete a file from Pocket Casts cloud storage."""
        self._check(self.client.delete(f"{BASE_URL}/files/{file_uuid}"))

    def mark_played(self, podcast_uuid, episode_uuid):
        try:
            self._post("/sync/update_episode", {
                "uuid":    episode_uuid,
                "podcast": podcast_uuid,
                "status":  3,
            })
        except Exception as e:
            return self._err(e)
        return None


# ─────────────────────────────────────────────
# MPV IPC
# ─────────────────────────────────────────────

class MPV:
    """Owns one mpv process and talks to it over its JSON IPC socket.

    Playback state is read once per UI tick by poll() and cached, so drawing
    never waits on the socket, and a reply that goes missing keeps the last
    good value instead of reporting position 0."""

    def __init__(self):
        self.sock = None
        self.proc = None
        self.path = None
        self._id   = 0
        self._gen  = 0      # bumped by launch() and quit(); a stale launch gives up
        self._buf  = b""
        self._lock = threading.RLock()
        self._reset_state()

    def _reset_state(self, pos=0.0):
        self.pos      = float(pos or 0)
        self.dur      = 0.0
        self.paused   = False
        self.chapter  = 0
        self.chapters = []
        self._tick    = 0

    @staticmethod
    def _kill(proc, path):
        try:
            proc.kill()
            proc.wait(timeout=1)
        except Exception:
            pass
        try:
            os.unlink(path)
        except OSError:
            pass

    def launch(self, url, speed=1.0, start_pos=0, skip_silence=0, title=""):
        """Start mpv and connect to it. Safe to call from a worker thread: a
        quit() or a newer launch() makes this one clean up and return False."""
        with self._lock:
            self._gen += 1
            gen = self._gen
            old = (self.proc, self.sock, self.path)
        if old[0]:
            # Normally quit() ran first; never leave a previous mpv behind
            self._kill(old[0], old[2] or "")
        self._teardown(*old)
        # One socket per process and per launch, so two pocketcli instances
        # (or two quick launches) never talk to each other's mpv
        path = os.path.join(_runtime_dir(), f"pocketcli-mpv-{os.getpid()}-{gen}.sock")
        try:
            os.unlink(path)
        except OSError:
            pass

        cmd = [
            "mpv", "--no-video",
            f"--input-ipc-server={path}",
            "--really-quiet",
            f"--speed={speed}",
        ]
        if start_pos and int(start_pos) > 0:
            cmd += [f"--start={int(start_pos)}"]
        if title:
            cmd += [f"--force-media-title={title}"]

        af = SILENCE_FILTERS.get(skip_silence)
        if af:
            cmd += [f"--af={af}"]

        # "--" ends the options: a URL from a feed is never read as a flag
        cmd += ["--", url]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return False

        with self._lock:
            if gen != self._gen:
                self._kill(proc, path)
                return False
            self.proc, self.path, self.sock, self._buf = proc, path, None, b""
            self._reset_state(start_pos)

        for _ in range(40):
            if proc.poll() is not None:
                break
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(path)
            except OSError:
                sock.close()
                with self._lock:
                    if gen != self._gen:
                        self._kill(proc, path)
                        return False
                time.sleep(0.1)
                continue
            with self._lock:
                if gen != self._gen:
                    sock.close()
                    self._kill(proc, path)
                    return False
                self.sock = sock
            return True

        # Never connected: do not leave an mpv we cannot control
        self._kill(proc, path)
        with self._lock:
            if gen == self._gen:
                self.proc = self.path = None
        return False

    def _cmd(self, cmd, timeout=0.5):
        """Send one command and return its reply data, or None.

        mpv also writes event lines on the same socket at any time, so this
        reads until the line carrying our request_id arrives, keeping any
        leftover bytes for the next call."""
        with self._lock:
            sock = self.sock
            if not sock:
                return None
            self._id += 1
            rid = self._id
            try:
                sock.settimeout(timeout)
                sock.sendall((json.dumps({"command": cmd, "request_id": rid}) + "\n").encode())
                deadline = time.time() + timeout
                while True:
                    while b"\n" in self._buf:
                        line, self._buf = self._buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            resp = json.loads(line)
                        except ValueError:
                            continue
                        if resp.get("request_id") == rid:
                            if resp.get("error", "success") != "success":
                                return None
                            return resp.get("data")
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return None
                    sock.settimeout(remaining)
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise OSError("mpv closed the socket")
                    self._buf += chunk
            except socket.timeout:
                return None
            except OSError:
                try:
                    sock.close()
                except OSError:
                    pass
                if self.sock is sock:
                    self.sock = None
                return None

    def poll(self):
        """Refresh the cached playback state. Called once per UI tick."""
        if not self.sock or not self.is_running():
            return
        pos = self._cmd(["get_property", "time-pos"])
        if not isinstance(pos, (int, float)) or isinstance(pos, bool):
            return  # slow or closing: keep the last good values this tick
        self.pos = float(pos)
        paused = self._cmd(["get_property", "pause"])
        if isinstance(paused, bool):
            self.paused = paused
        if self._tick % 10 == 0:
            dur = self._cmd(["get_property", "duration"])
            if isinstance(dur, (int, float)) and not isinstance(dur, bool):
                self.dur = float(dur)
            ch = self._cmd(["get_property", "chapter"])
            self.chapter = ch if isinstance(ch, int) and not isinstance(ch, bool) else 0
            chapters = self._cmd(["get_property", "chapter-list"])
            self.chapters = chapters if isinstance(chapters, list) else []
        self._tick += 1

    # Cached properties (see poll)
    def get_position(self):      return self.pos
    def get_duration(self):      return self.dur
    def get_paused(self):        return self.paused
    def get_chapter(self):       return self.chapter
    def get_chapter_list(self):  return self.chapters

    # Commands
    def next_chapter(self):
        self._cmd(["add", "chapter",  1]); self._tick = 0
    def prev_chapter(self):
        self._cmd(["add", "chapter", -1]); self._tick = 0
    def seek(self, secs):
        self._cmd(["seek", secs, "relative"])
    def set_speed(self, s):
        self._cmd(["set_property", "speed", s])

    def pause_toggle(self):
        self._cmd(["cycle", "pause"])
        paused = self._cmd(["get_property", "pause"])
        if isinstance(paused, bool):
            self.paused = paused

    def pause(self):
        """Pause (unlike pause_toggle, never resumes an already paused player)."""
        self._cmd(["set_property", "pause", True])
        self.paused = True

    def set_skip_silence(self, level):
        """Apply a skip silence level to the running mpv right away."""
        self._cmd(["af", "set", SILENCE_FILTERS.get(level) or ""])

    def _teardown(self, proc, sock, path):
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
        with self._lock:
            if self.proc is proc:
                self.proc = None
            if self.sock is sock:
                self.sock = None
            if self.path == path:
                self.path = None
            self._buf = b""

    def quit(self):
        with self._lock:
            self._gen += 1   # cancels a launch() still waiting to connect
            proc, sock, path = self.proc, self.sock, self.path
        if sock:
            self._cmd(["quit"], timeout=0.3)
        if proc:
            try:
                if not sock:
                    proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                self._kill(proc, path or "")
        self._teardown(proc, sock, path)

    def reap(self):
        """Clean up after mpv exited by itself. Returns its exit code."""
        with self._lock:
            proc, sock, path = self.proc, self.sock, self.path
        code = proc.poll() if proc else None
        self._teardown(proc, sock, path)
        return code

    def is_running(self):
        proc = self.proc
        return proc is not None and proc.poll() is None

    def has_exited(self):
        """True when an mpv we started has ended and was not cleaned up yet."""
        proc = self.proc
        return proc is not None and proc.poll() is not None

# ─────────────────────────────────────────────
# Login screen
# ─────────────────────────────────────────────

# Login screen ASCII art
_POCKET_ART = [
    r"██████╗  ██████╗  ██████╗██╗  ██╗███████╗████████╗",
    r"██╔══██╗██╔═══██╗██╔════╝██║ ██╔╝██╔════╝╚══██╔══╝",
    r"██████╔╝██║   ██║██║     █████╔╝ █████╗     ██║   ",
    r"██╔═══╝ ██║   ██║██║     ██╔═██╗ ██╔══╝     ██║   ",
    r"██║     ╚██████╔╝╚██████╗██║  ██╗███████╗   ██║   ",
]
_CLI_ART = [
    r" ██████╗██╗     ██╗",
    r"██╔════╝██║     ██║",
    r"██║     ██║     ██║",
    r"██║     ██║     ██║",
    r"╚██████╗███████╗██║",
]
_TAGLINES = [
    "the unofficial pocket casts terminal client.",
    "your pocket casts. your terminal.",
    "no browser. no electron. just audio.",
    "pocket casts... a bit different.",
    "pocket casts, without leaving the terminal.",
]


def curses_login(stdscr):
    """Full-screen login UI with ASCII art header and blinking cursor.

    Flow:
      1. Draw POCKET (orange) + CLI (green) ASCII art, tagline, separator.
      2. Blink '█' cursor at the end of the last CLI art line until any key
         is pressed - that keypress is discarded (it is not part of the email).
      3. Show Email / Password prompts and collect credentials.
      4. POST to Pocket Casts login endpoint and save the token.

    Returns:
        (token, None)  on success
        (None, error)  on failure
    """
    # ── Color pairs ──────────────────────────────────────────────────────────
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED,   -1)   # POCKET - warm red/orange
    curses.init_pair(2, curses.COLOR_GREEN, -1)   # CLI - matrix green
    curses.init_pair(3, curses.COLOR_WHITE, -1)   # tagline / separator

    curses.curs_set(0)    # hide text cursor during art phase
    curses.noecho()
    stdscr.clear()

    h, w     = stdscr.getmaxyx()
    tagline  = random.choice(_TAGLINES)

    # ── Layout math ──────────────────────────────────────────────────────────
    # Total art height: POCKET rows + CLI rows
    art_rows  = len(_POCKET_ART) + len(_CLI_ART)
    # Full block: art + blank + tagline + blank + separator + blank + email + blank + password
    block_h   = art_rows + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1
    top       = max(1, (h - block_h) // 2)

    # Horizontal anchor: center the wider POCKET block
    art_w     = len(_POCKET_ART[0])
    cx        = max(0, (w - art_w) // 2)

    # CLI and cursor share the same left anchor as POCKET
    cli_cx    = cx

    # Row positions (computed once, reused everywhere)
    pocket_rows = [top + i for i in range(len(_POCKET_ART))]
    cli_start   = top + len(_POCKET_ART)
    cli_rows    = [cli_start + i for i in range(len(_CLI_ART))]
    cursor_row  = cli_rows[-1]                    # last CLI art row
    cursor_col  = cli_cx + len(_CLI_ART[0])       # immediately right of last char
    tagline_row = cli_rows[-1] + 2
    sep_row     = tagline_row + 2
    email_row   = sep_row + 2
    pass_row    = email_row + 2

    # ── Static draw ──────────────────────────────────────────────────────────
    def draw_static():
        stdscr.clear()

        # POCKET in orange/red bold
        for i, line in enumerate(_POCKET_ART):
            try:
                stdscr.addstr(pocket_rows[i], cx, line,
                              curses.color_pair(1) | curses.A_BOLD)
            except Exception:
                pass

        # CLI in matrix green bold, left-aligned with POCKET
        for i, line in enumerate(_CLI_ART):
            try:
                stdscr.addstr(cli_rows[i], cli_cx, line,
                              curses.color_pair(2) | curses.A_BOLD)
            except Exception:
                pass

        # Tagline - centered horizontally
        try:
            tl_col = max(0, (w - len(tagline)) // 2)
            stdscr.addstr(tagline_row, tl_col, tagline, curses.color_pair(3))
        except Exception:
            pass

        # Separator - same width and left edge as POCKET
        try:
            stdscr.addstr(sep_row, cx, "─" * min(art_w, w - cx),
                          curses.color_pair(3))
        except Exception:
            pass

        # "press any key" hint below separator
        hint = "press any key to continue"
        try:
            stdscr.addstr(sep_row + 1, cx, hint, curses.color_pair(3))
        except Exception:
            pass

        stdscr.refresh()

    draw_static()

    # ── Blinking cursor ───────────────────────────────────────────────────────
    # Runs in a daemon thread; stopped the moment the user presses any key.
    stop_blink = threading.Event()

    def _blink():
        visible = True
        while not stop_blink.is_set():
            char = "█" if visible else " "
            try:
                stdscr.addstr(cursor_row, cursor_col, char,
                              curses.color_pair(2) | curses.A_BOLD)
                stdscr.refresh()
            except Exception:
                pass
            visible = not visible
            stop_blink.wait(0.5)

    blink_thread = threading.Thread(target=_blink, daemon=True)
    blink_thread.start()

    # Block until any key to stop the blink animation.
    # We save the key in case it is a printable character (first letter of email).
    stdscr.nodelay(False)
    first_key = stdscr.getch()

    # Stop blink, erase cursor and hint
    stop_blink.set()
    blink_thread.join()
    try:
        stdscr.addstr(cursor_row, cursor_col, " ")
    except Exception:
        pass
    try:
        stdscr.addstr(sep_row + 1, cx, " " * 30)
    except Exception:
        pass

    # ── Credential input ──────────────────────────────────────────────────────
    curses.curs_set(1)
    curses.echo()

    try:
        stdscr.addstr(email_row, cx, "Email    : ", curses.color_pair(1))
    except Exception:
        pass
    stdscr.refresh()

    # If the first key was a printable char, display it and prepend to input
    prefix = ""
    if 32 <= first_key <= 126:
        prefix = chr(first_key)
        try:
            stdscr.addstr(email_row, cx + 11, prefix)
        except Exception:
            pass
        stdscr.refresh()

    rest  = stdscr.getstr(email_row, cx + 11 + len(prefix), 60 - len(prefix)).decode().strip()
    email = (prefix + rest).strip()

    curses.noecho()   # hide password characters

    try:
        stdscr.addstr(pass_row, cx, "Password : ", curses.color_pair(1))
    except Exception:
        pass
    stdscr.refresh()
    password = stdscr.getstr(pass_row, cx + 11, 60).decode().strip()

    # ── Authenticate - retry loop ─────────────────────────────────────────────
    while True:
        curses.curs_set(0)
        try:
            stdscr.addstr(pass_row + 2, cx, "Authenticating...          ", curses.color_pair(2))
        except Exception:
            pass
        stdscr.refresh()

        try:
            r = httpx.post(
                f"{BASE_URL}/user/login",
                json={"email": email, "password": password, "scope": "webplayer"},
                timeout=10,
            )
            r.raise_for_status()
            data  = r.json()
            token = data.get("token")
            if not token:
                raise ValueError("No token in response")
            save_config(email, token, data.get("uuid", ""))
            return token, None

        except Exception as e:
            # Show error and let user retry password
            err_msg = "Invalid credentials. Try again." if "401" in str(e) else f"Error: {e}"
            try:
                stdscr.addstr(pass_row + 2, cx, f"  {err_msg[:art_w - 2]}  ",
                              curses.color_pair(1) | curses.A_BOLD)
            except Exception:
                pass
            stdscr.refresh()

            # Clear password field and retry
            try:
                stdscr.addstr(pass_row, cx, "Password : " + " " * 60,
                              curses.color_pair(1))
            except Exception:
                pass
            stdscr.refresh()
            curses.curs_set(1)
            curses.noecho()
            password = stdscr.getstr(pass_row, cx + 11, 60).decode().strip()


# ─────────────────────────────────────────────
# TUI
# ─────────────────────────────────────────────

class PocketTUI:

    # View identifiers
    VIEW_PODCASTS = "podcasts"
    VIEW_EPISODES = "episodes"
    VIEW_QUEUE    = "queue"      # in_progress | new | starred | up_next
    VIEW_FILES    = "files"
    VIEW_DISCOVER = "discover"

    # Focus levels
    FOCUS_CONTENT = 0   # list navigation (default)
    FOCUS_TABBAR  = 1   # top tab bar
    FOCUS_SUBMENU = 2   # discover mode bar

    # Color pair semantics (applied by _apply_theme)
    # 1=accent  2=active/green  3=info/yellow  4=normal
    # 5=selection  6=header  7=error  8=subtitle/dim

    def __init__(self, stdscr, api):
        self.scr = stdscr
        self.api = api
        self.mpv = MPV()

        # ── Navigation state ──
        self.view       = self.VIEW_PODCASTS
        self.podcasts   = []
        self.pods_loaded = False     # False until the first podcast list answer
        self.episodes   = []
        self.queue_items = []
        self.files_items = []
        self.queue_mode  = "in_progress"   # in_progress | new | starred | up_next
        self.current_pod = None

        # List cursors and scroll offsets per view
        self.pod_cursor = self.pod_offset = 0
        self.ep_cursor  = self.ep_offset  = 0
        self.q_cursor   = self.q_offset   = 0
        self.f_cursor   = self.f_offset   = 0

        # ── Focus / Tab navigation ──
        self.focus_level          = self.FOCUS_CONTENT
        self.tab_cursor           = 0
        self.discover_mode_cursor = 0

        # ── Player state ──
        prefs = load_prefs()
        self.playing_pod  = None
        self.playing_ep   = None
        self.speed_idx    = prefs["speed_idx"]      # index into SPEEDS; default 1.0x
        self.skip_silence = prefs["skip_silence"]   # 0=off 1=normal 2=medium 3=aggressive
        self.last_sync    = 0
        self.loading_stream = False  # True while a stream URL is fetched / mpv starts
        self._play_gen      = 0      # bumped per play request; stale workers give up
        self._sync_warned   = False  # a sync failure is reported once per episode
        self._quit          = False
        self.sleep_timer_end  = 0    # epoch when timer fires, 0=inactive
        self.show_sleep_menu  = False
        self.sleep_cursor     = 0

        # ── Overlays ──
        self.show_desc   = False
        self.desc_offset = 0
        self.show_keys   = False
        self.keys_offset = 0
        self.show_themes = False
        self.theme_cursor = 0

        # ── Search (episodes / podcasts tab) ──
        self.searching          = False
        self.search_query       = ""
        self.search_results     = []     # episode search results
        self.search_cursor      = self.search_offset     = 0
        self.pod_search_results = []     # podcast search results
        self.pod_search_cursor  = self.pod_search_offset = 0

        # ── Discover / subscribe ──
        self.discover_query     = ""
        self.discover_results   = []
        self.discover_cursor    = self.discover_offset = 0
        self.discover_searching = False
        self.subscribed_uuids   = set()
        # Curated lists: "trending" | "popular" | "featured"
        self.discover_list_mode = "trending"
        self.discover_lists     = {}   # cache: mode -> list of podcasts

        # ── Unsubscribe confirm ──
        self.unsub_confirm = False
        self.unsub_target  = None

        # ── Delete file confirm ──
        # step: 0=inactive, 1=first confirm, 2=second confirm (unplayed/in-progress)
        self.del_file_step   = 0
        self.del_file_target = None

        # ── Status bar ──
        self.status_msg   = ""
        self.status_error = False
        self.status_timer = 0

        # ── Theme setup ──
        self.THEMES        = _load_themes()
        self.current_theme = next(
            (i for i, t in enumerate(self.THEMES) if t["name"] == prefs["theme"]), 0)

        curses.start_color()
        curses.use_default_colors()
        self._truecolor = _can_redefine_colors()
        self._tc_ids    = list(range(16, 25))
        self._apply_theme(self.current_theme)

        curses.curs_set(0)
        self.scr.nodelay(True)
        self.scr.keypad(True)

    # ─────────────────────────────────────────
    # Theme
    # ─────────────────────────────────────────

    def _apply_theme(self, idx):
        t  = self.THEMES[idx]
        tc = self._truecolor

        def color(hex_val, slot):
            if tc and hex_val:
                cid = self._tc_ids[slot]
                if _hex_to_curses_color(hex_val, cid):
                    return cid
            if not hex_val:
                return curses.COLOR_WHITE
            # No palette redefinition: nearest fixed color the terminal has
            return _hex_to_256(hex_val) if curses.COLORS >= 256 else _hex_to_ansi(hex_val)

        accent = color(t["accent"],    0)
        active = color(t["green"],     1)
        info   = color(t["yellow"],    2)
        sel_fg = color(t["bright_fg"], 3)
        error  = color(t["red"],       5)
        sub    = color(t["fg"],        6)
        sel_bg = color(t["fg"],        7)

        curses.init_pair(1, accent,             -1)        # accent / title
        curses.init_pair(2, active,             -1)        # active / playing
        curses.init_pair(3, info,               -1)        # secondary / muted
        curses.init_pair(4, curses.COLOR_WHITE, -1)        # normal text
        curses.init_pair(5, sel_fg,             sel_bg)    # selection highlight
        curses.init_pair(6, accent,             -1)        # header bar
        curses.init_pair(7, error,              -1)        # error / danger
        curses.init_pair(8, sub,                -1)        # subtitle / dim

    # ─────────────────────────────────────────
    # Data loading
    # ─────────────────────────────────────────

    def load_podcasts(self):
        self.status("Loading podcasts...")
        def _load():
            try:
                pods = self.api.subscribed_podcasts()
                pods.sort(key=lambda p: p.get("title", "").lower())
                self.podcasts         = pods
                self.subscribed_uuids = {p.get("uuid", "") for p in pods}
                self.pods_loaded      = True
                self.status("")
            except Exception as e:
                self.pods_loaded = True
                self.status(f"Error: {e}", error=True)
        threading.Thread(target=_load, daemon=True).start()

    def load_episodes(self, podcast):
        self.current_pod = podcast
        self.view        = self.VIEW_EPISODES
        self.episodes    = []
        self.ep_cursor   = self.ep_offset = 0
        self.status(f"Loading {podcast.get('title', '')}...")

        # Generation counter prevents stale results from overwriting newer ones
        self._load_gen = getattr(self, "_load_gen", 0) + 1
        gen = self._load_gen

        def _load():
            try:
                feed_url = podcast.get("url") or podcast.get("feedUrl") or None
                if gen != self._load_gen:
                    return
                eps = self.api.podcast_episodes(
                    podcast["uuid"], podcast.get("title", ""), feed_url=feed_url
                )
                if gen != self._load_gen:
                    return
                self.episodes = eps
                self.ep_cursor = self.ep_offset = 0
                if not self.episodes:
                    self.status("No episodes found. Feed may not be publicly available.", error=True)
                else:
                    self.status(f"Loaded {len(self.episodes)} episodes")
            except Exception as e:
                if gen == self._load_gen:
                    self.status(f"Error loading episodes: {e}", error=True)
        threading.Thread(target=_load, daemon=True).start()

    def load_queue(self, keep_cursor=False):
        self.status("Loading...")
        mode = self.queue_mode
        def _load():
            try:
                if mode == "in_progress":
                    items = self.api.in_progress()
                elif mode == "new":
                    items = self.api.new_releases()
                elif mode == "up_next":
                    items  = self.api.up_next_list()
                    titles = {p.get("uuid"): p.get("title", "") for p in self.podcasts}
                    # Up Next mixes episodes and uploaded files. A file must be
                    # played through the Files API, so tell them apart here.
                    try:
                        files = {f.get("uuid"): f for f in self.api.files()}
                    except Exception:
                        files = {f.get("uuid"): f for f in self.files_items}
                    for ep in items:
                        ep.setdefault("podcastUuid", ep.get("podcast", ""))
                        if ep.get("uuid") in files or ep.get("podcast") == FILE_PODCAST_UUID:
                            ep["file"]         = files.get(ep.get("uuid")) or {
                                "uuid": ep.get("uuid"), "title": ep.get("title", "")}
                            ep["podcastTitle"] = "Files"
                            for k in ("duration", "playedUpTo", "playingStatus"):
                                if k in ep["file"]:
                                    ep.setdefault(k, ep["file"][k])
                        else:
                            ep.setdefault("podcastTitle", titles.get(ep.get("podcast"), ""))
                else:
                    items = self.api.starred()
                if mode != self.queue_mode:
                    return  # the user switched tabs while this was loading
                self.queue_items = items
                if keep_cursor:
                    self.q_cursor = min(self.q_cursor, max(0, len(items) - 1))
                    self.q_offset = min(self.q_offset, self.q_cursor)
                else:
                    self.q_cursor = self.q_offset = 0
                self.status("")
            except Exception as e:
                self.status(f"Error: {e}", error=True)
        threading.Thread(target=_load, daemon=True).start()

    def load_files(self):
        self.status("Loading files...")
        def _load():
            try:
                files = self.api.files()
                files.sort(key=lambda f: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', f.get('title', ''))])
                self.files_items = files
                self.f_cursor = self.f_offset = 0
                self.status("")
            except Exception as e:
                self.status(f"Error: {e}", error=True)
        threading.Thread(target=_load, daemon=True).start()

    def load_discover_list(self, mode=None):
        if mode:
            self.discover_list_mode = mode
        m = self.discover_list_mode
        # Use cache if available and not searching
        if m in self.discover_lists and not self.discover_query:
            self.discover_results  = self.discover_lists[m]
            self.discover_cursor   = self.discover_offset = 0
            return
        self.status(f"Loading {m}...")
        def _load():
            try:
                pods = self.api.curated_list(m)
                self.discover_lists[m] = pods
                # Only apply if still in same mode and not searching
                if self.discover_list_mode == m and not self.discover_query:
                    self.discover_results = pods
                    self.discover_cursor  = self.discover_offset = 0
                self.status("")
            except Exception as e:
                self.status(f"Error loading {m}: {e}", error=True)
        threading.Thread(target=_load, daemon=True).start()

    # ─────────────────────────────────────────
    # Player
    # ─────────────────────────────────────────

    def _stop_current(self):
        """Sync position and stop mpv if something is playing."""
        self._play_gen += 1          # cancels a play request still in flight
        self.loading_stream = False
        if self.mpv.is_running() and self.playing_pod and self.playing_ep:
            pos = self.mpv.get_position()
            self._remember_position(pos)
            self._push_sync(pos)
        self.mpv.quit()

    def _remember_position(self, pos):
        """Keep the local copy of the episode in step with what was played, so
        the lists and a later resume do not wait for the next refresh."""
        if self.playing_ep and pos and pos >= 1:
            self.playing_ep["playedUpTo"] = int(pos)
            if int(self.playing_ep.get("playingStatus") or 0) != 3:
                self.playing_ep["playingStatus"] = 2

    def _push_sync(self, pos, status=2, wait=False):
        """Push position to the API for the current file or episode.
        status 3 marks it as played. wait=True blocks briefly (used on exit)."""
        pod = self.playing_pod
        ep  = self.playing_ep
        if not pod or not ep or not pod.get("uuid"):
            return
        if ep.get("unresolved"):
            return  # Pocket Casts has no id for this episode: nothing to sync to
        if status == 2 and (not pos or pos < 1):
            return  # never overwrite real progress with a position of zero

        def _sync():
            if pod["uuid"] == "__files__":
                err = self.api.sync_file(ep["uuid"], pos, status)
            elif status == 3:
                err = self.api.mark_played(pod["uuid"], ep["uuid"])
            else:
                err = self.api.sync_episode(pod["uuid"], ep["uuid"], pos)
            if not err:
                self._sync_warned = False
            elif not self._sync_warned:
                self._sync_warned = True
                self.status(f"Sync failed: {err}", error=True)

        t = threading.Thread(target=_sync, daemon=True)
        t.start()
        if wait:
            t.join(timeout=5)

    def _begin_playback(self, pod, ep, get_url, missing_msg):
        """Stop what is playing and start ep. Fetching the stream URL and
        starting mpv happen in a worker so the UI never freezes."""
        self._stop_current()
        self.playing_pod    = pod
        self.playing_ep     = ep
        self._sync_warned   = False
        self.loading_stream = True
        self.last_sync      = time.time()   # first periodic sync is 30s from now
        gen   = self._play_gen
        title = ep.get("title", "")
        self.status("Fetching stream...")

        def _run():
            try:
                url = get_url()
            except Exception:
                url = None
            if gen != self._play_gen:
                return
            if not url:
                self.loading_stream = False
                self.status(missing_msg, error=True)
                return

            start = resume_start(
                ep.get("playedUpTo") or ep.get("played_up_to"),
                int(ep.get("playingStatus") or 0),
            )
            ok = self.mpv.launch(url, speed=SPEEDS[self.speed_idx], start_pos=start,
                                 skip_silence=self.skip_silence, title=title)
            if gen != self._play_gen:
                return
            self.loading_stream = False
            if not ok:
                self.status("Could not start mpv (is it installed?)", error=True)
                return

            self.last_sync = time.time()
            if ep.get("unresolved"):
                self.status("Playing. Pocket Casts does not list this episode: progress will not sync")
            else:
                self.status(f"Playing: {title[:50]}")
            self._announce_playing(pod, ep, url, gen)

        threading.Thread(target=_run, daemon=True).start()

    def _announce_playing(self, pod, ep, url, gen):
        """Make the episode the current item of Up Next, which is what other
        devices show as "now playing". Runs in the playback worker thread."""
        if pod.get("uuid") == "__files__":
            return
        payload = self.api.up_next_episode(pod.get("uuid"), ep, url)
        if not payload:
            if not ep.get("unresolved"):
                # Say why, so a list that lacks a field does not fail silently
                have = {"uuid": ep.get("uuid"), "podcast": pod.get("uuid"), "title": ep.get("title"),
                        "url": ep.get("url") or ep.get("streamUrl") or url,
                        "published": ep.get("published") or ep.get("publishedAt")}
                missing = ", ".join(k for k, v in have.items() if not v) or "a valid id"
                self.status(f"Playing. Not sent to Up Next: no {missing}")
            return
        err = self.api.up_next_add("now", payload)
        if gen != self._play_gen:
            return
        if err:
            self.status(f"Up Next failed: {err}", error=True)
        elif self._ctx() == "upnext":
            self.load_queue(keep_cursor=True)

    def play(self, podcast_dict, episode_dict):
        def _url():
            url = None
            if not episode_dict.get("unresolved"):
                url = self.api.episode_stream_url(podcast_dict["uuid"], episode_dict["uuid"])
            return url or episode_dict.get("url") or episode_dict.get("streamUrl")
        self._begin_playback(podcast_dict, episode_dict, _url, "Could not get episode URL")

    def play_file(self, file_dict):
        self._begin_playback(
            {"uuid": "__files__", "title": "Files"}, file_dict,
            lambda: self.api.file_stream_url(file_dict["uuid"]),
            "Could not get file URL",
        )

    def sync_position(self):
        """Periodic sync every 30s while playing."""
        if not self.mpv.is_running() or not self.playing_pod or not self.playing_ep:
            return
        now = time.time()
        if now - self.last_sync >= 30:
            self.last_sync = now
            pos = self.mpv.get_position()
            self._remember_position(pos)
            self._push_sync(pos)

    def check_sleep_timer(self):
        """Pause playback when sleep timer expires."""
        if not self.sleep_timer_end or not self.mpv.is_running():
            return
        if time.time() >= self.sleep_timer_end:
            self.sleep_timer_end = 0
            pos = self.mpv.get_position()
            self._remember_position(pos)
            self._push_sync(pos)
            self.mpv.pause()
            self.status("Sleep timer: paused.")

    def check_finished(self):
        """React to mpv ending by itself.

        mpv exits with 0 when the file played to its end. Only then, and only
        near the end of the episode, is it marked as played. Any other exit
        (bad URL, network error, crash) keeps the position instead, so a
        failed stream never shows up as "played" in Pocket Casts."""
        if self.loading_stream or not self.mpv.has_exited():
            return
        pos  = self.mpv.get_position()
        dur  = self.mpv.get_duration()
        code = self.mpv.reap()
        pod, ep = self.playing_pod, self.playing_ep
        if not pod or not ep:
            return
        if not dur:
            dur = float(ep.get("duration") or 0)

        # With skip silence the reported position runs behind the real one,
        # so there the clean exit code alone decides.
        ended = code == 0 and (is_finished(pos, dur) or self.skip_silence or not dur)
        title = ep.get("title", "")[:50]
        if ended:
            ep["playingStatus"] = 3
            ep["playedUpTo"]    = int(dur or pos)
            self._push_sync(dur or pos, status=3)
            if pod.get("uuid") != "__files__" and not ep.get("unresolved"):
                uuid = ep.get("uuid", "")
                threading.Thread(target=lambda: self.api.up_next_remove([uuid]), daemon=True).start()
            self.status(f"Finished: {title}")
            self.playing_ep  = None
            self.playing_pod = None
        else:
            self._remember_position(pos)
            self._push_sync(pos)
            self.status(f"Playback stopped (mpv exit code {code}). Press space to resume.", error=True)

    # ─────────────────────────────────────────
    # Subscribe / Unsubscribe actions
    # ─────────────────────────────────────────

    def _do_subscribe(self, pod):
        title    = pod.get("title", "")
        feed_url = pod.get("feedUrl", "")
        raw_uuid = pod.get("uuid", "")

        # Determine if uuid is already a real PC uuid (has dashes, not purely numeric)
        # PC uuids look like: 395bad80-26fe-0139-32ce-0acc26574db2
        # iTunes collectionIds are purely numeric: 1234567890
        is_pc_uuid = "-" in raw_uuid and not raw_uuid.isdigit()

        if raw_uuid in self.subscribed_uuids:
            self.status(f"Already subscribed to {title}")
            return

        self.status(f"Subscribing to {title}...")

        def _sub():
            try:
                if is_pc_uuid:
                    # From curated list: UUID is already the real PC uuid
                    pc_uuid = raw_uuid
                else:
                    # From iTunes search: resolve via feed URL
                    pc_uuid = self.api.resolve_podcast_uuid(feed_url) if feed_url else None
                    if not pc_uuid:
                        self.status(f"Could not resolve UUID for {title}", error=True)
                        return

                if pc_uuid in self.subscribed_uuids:
                    self.status(f"Already subscribed to {title}")
                    return

                self.api.subscribe_podcast(pc_uuid)
                self.subscribed_uuids.add(pc_uuid)
                pods = self.api.subscribed_podcasts()
                pods.sort(key=lambda p: p.get("title", "").lower())
                self.podcasts = pods
                self.status(f"Subscribed to {title}!")
            except Exception as e:
                self.status(f"Subscribe error: {e}", error=True)

        threading.Thread(target=_sub, daemon=True).start()

    def _do_unsubscribe(self):
        pod = self.unsub_target
        self.unsub_confirm = False
        self.unsub_target  = None
        if not pod:
            return
        uuid  = pod.get("uuid", "")
        title = pod.get("title", "")
        self.status(f"Unsubscribing from {title}...")
        def _unsub():
            try:
                self.api.unsubscribe_podcast(uuid)
                self.podcasts = [p for p in self.podcasts if p.get("uuid") != uuid]
                self.subscribed_uuids.discard(uuid)
                self.pod_cursor = min(self.pod_cursor, max(0, len(self.podcasts) - 1))
                self.status(f"Unsubscribed from {title}.")
            except Exception as e:
                self.status(f"Unsubscribe error: {e}", error=True)
        threading.Thread(target=_unsub, daemon=True).start()

    # ─────────────────────────────────────────
    # Search helpers
    # ─────────────────────────────────────────

    def _update_search_results(self):
        q = self.search_query.lower().strip()
        if self.view == self.VIEW_EPISODES:
            self.search_results = [
                ep for ep in self.episodes if q in ep.get("title", "").lower()
            ] if q else []
            self.search_cursor = self.search_offset = 0
        elif self.view == self.VIEW_PODCASTS:
            if len(q) >= 2:
                self.status("Searching...")
                def _search():
                    self.pod_search_results = self.api.search_podcasts(self.search_query)
                    self.pod_search_cursor  = self.pod_search_offset = 0
                    self.status("")
                threading.Thread(target=_search, daemon=True).start()
            else:
                self.pod_search_results = []
                self.pod_search_cursor  = self.pod_search_offset = 0

    def _update_discover_results(self):
        q = self.discover_query.strip()
        if len(q) < 2:
            self.discover_results = []
            self.discover_cursor  = self.discover_offset = 0
            return
        self.status("Searching...")
        def _search():
            try:
                self.discover_results = self.api.search_podcasts(q)
                self.discover_cursor  = self.discover_offset = 0
                self.status(f"{len(self.discover_results)} results" if self.discover_results else "No results.")
            except Exception as e:
                self.status(f"Search error: {e}", error=True)
        threading.Thread(target=_search, daemon=True).start()

    def _load_episodes_from_feed(self, pod):
        """Load episodes for a podcast found via search (may not be subscribed)."""
        self.current_pod = pod
        self.status(f"Loading {pod.get('title', '')}...")
        def _load():
            try:
                feed_url = pod.get("feedUrl") or self.api.podcast_feed_url(pod.get("title", ""))
                eps      = self.api.podcast_episodes_from_rss(feed_url) if feed_url else []

                # A search result only carries an iTunes id. Ask Pocket Casts
                # for its own ids so progress can sync; without them the
                # episodes still play, flagged as unresolved.
                pc_uuid = self.api.resolve_podcast_uuid(feed_url) if feed_url else None
                cache   = []
                if pc_uuid:
                    try:
                        cache = self.api.podcast_cache_episodes(pc_uuid)
                    except Exception:
                        cache = []
                if cache:
                    pod["uuid"] = pc_uuid
                    self.api.attach_real_uuids(eps, cache)
                    self.api.merge_states(pc_uuid, eps)
                else:
                    for ep in eps:
                        ep["unresolved"] = True

                self.episodes  = eps
                self.ep_cursor = self.ep_offset = 0
                self.view      = self.VIEW_EPISODES
                self.status(f"Loaded {len(self.episodes)} episodes")
            except Exception as e:
                self.status(f"Error: {e}", error=True)
        threading.Thread(target=_load, daemon=True).start()

    # ─────────────────────────────────────────
    # Status bar
    # ─────────────────────────────────────────

    def status(self, msg, error=False):
        self.status_msg   = msg
        self.status_error = error
        self.status_timer = time.time()

    # ─────────────────────────────────────────
    # Drawing
    # ─────────────────────────────────────────

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()

        self._draw_header(w)
        self._draw_tabs(w)
        self._draw_separator(2, w)

        player_h  = 6 if (self.mpv.is_running() or self.playing_ep) else 0
        content_h = h - 3 - player_h - 1

        self._draw_content(3, content_h, w)

        if player_h:
            self._draw_separator(h - player_h - 1, w, label=self._now_playing_label())
            self._draw_player(h - player_h, w)

        self._draw_footer(h - 1, w)

        # Overlays, bottom-up: the one that owns the keys is painted last
        for ov in reversed(OVERLAYS):
            if ov.draw and ov.is_open(self):
                getattr(self, ov.draw)()

        self.scr.refresh()

    def _now_playing_label(self):
        if not self.playing_ep:
            return ""
        paused = self.mpv.is_running() and self.mpv.get_paused()
        state  = "⏸ PAUSED" if paused else "▶ NOW PLAYING"
        return f" {state} "

    def _draw_header(self, w):
        self.scr.attron(curses.color_pair(6) | curses.A_BOLD)
        self.scr.addstr(0, 0, " " * w)
        self.scr.addstr(0, 0, f" P O C K E T C L I  v{VERSION}")
        self.scr.attroff(curses.color_pair(6) | curses.A_BOLD)
        if self.view == self.VIEW_EPISODES and self.current_pod:
            bc = trunc(self.current_pod.get("title", ""), 30)
            self.scr.attron(curses.color_pair(6))
            try:
                self.scr.addstr(0, w - len(bc) - 2, f"{bc} ")
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(6))

    def _current_tab_idx(self):
        """Return index in TABS matching current view/queue_mode."""
        for i, (_, _, view, qmode) in enumerate(TABS):
            if view == "queue":
                if self.view == self.VIEW_QUEUE and self.queue_mode == qmode:
                    return i
            elif view == "podcasts":
                if self.view in (self.VIEW_PODCASTS, self.VIEW_EPISODES):
                    return i
            elif view == self.view:
                return i
        return 0

    def _activate_tab(self, idx):
        """Switch to the tab at index idx."""
        _, _, view, qmode    = TABS[idx]
        self.tab_cursor      = idx
        self.focus_level     = self.FOCUS_CONTENT

        if view == "podcasts":
            self.view = self.VIEW_PODCASTS
            if not self.podcasts:
                self.load_podcasts()
        elif view == "queue":
            self.view       = self.VIEW_QUEUE
            self.queue_mode = qmode
            self.load_queue()
        elif view == "files":
            self.view = self.VIEW_FILES
            if not self.files_items:
                self.load_files()
        elif view == "discover":
            self.view             = self.VIEW_DISCOVER
            self.subscribed_uuids = {p.get("uuid", "") for p in self.podcasts}
            if not self.discover_query and not self.discover_results:
                self.load_discover_list()

    def _draw_tabs(self, w):
        """Tab bar: active=green, focused(FOCUS_TABBAR)=reverse, others=dim."""
        active_idx = self._current_tab_idx()
        full_w  = 1 + sum(len(f"[{k}] {lbl}") + 2 for k, lbl, _, _ in TABS)
        compact = full_w > w   # narrow terminal: only the active tab keeps its name
        x = 1
        for i, (key, label, _, _) in enumerate(TABS):
            is_active  = i == active_idx
            is_focused = (self.focus_level == self.FOCUS_TABBAR and i == self.tab_cursor)
            tag = f"[{key}] {label}" if (not compact or is_active or is_focused) else f"[{key}]"

            if is_focused:
                self.scr.attron(curses.A_REVERSE | curses.A_BOLD)
            elif is_active:
                self.scr.attron(curses.color_pair(2) | curses.A_BOLD)
            else:
                self.scr.attron(curses.color_pair(3))

            try:
                self.scr.addstr(1, x, tag)
            except Exception:
                pass

            if is_focused:
                self.scr.attroff(curses.A_REVERSE | curses.A_BOLD)
            elif is_active:
                self.scr.attroff(curses.color_pair(2) | curses.A_BOLD)
            else:
                self.scr.attroff(curses.color_pair(3))

            x += len(tag) + 2

    def _do_delete_file(self):
        """Delete the target file from cloud and remove from local list."""
        f     = self.del_file_target
        self.del_file_step   = 0
        self.del_file_target = None
        if not f:
            return
        uuid  = f.get("uuid", "")
        title = f.get("title", "")
        self.status(f"Deleting {title}...")
        def _delete():
            try:
                self.api.delete_file(uuid)
                self.files_items = [x for x in self.files_items if x.get("uuid") != uuid]
                self.f_cursor    = min(self.f_cursor, max(0, len(self.files_items) - 1))
                self.status(f"Deleted {title}.")
            except Exception as e:
                self.status(f"Delete error: {e}", error=True)
        threading.Thread(target=_delete, daemon=True).start()

    def _draw_delete_file_overlay(self):
        """Overlay for file delete confirmation (1 or 2 steps)."""
        if self.del_file_step == 0 or not self.del_file_target:
            return
        h, w  = self.scr.getmaxyx()
        f     = self.del_file_target
        title = f.get("title", "this file")
        dur   = int(f.get("duration", 0) or 0)
        pos   = int(f.get("playedUpTo", 0) or 0)

        is_second = self.del_file_step == 2

        if is_second:
            warn  = "Not finished! Delete from cloud anyway?"
            msg   = trunc(title, 44)
            ow    = max(len(warn) + 8, len(msg) + 8, 56)
            oh    = 7
        else:
            msg   = f"Delete from cloud: {trunc(title, 36)}?"
            ow    = max(len(msg) + 8, 52)
            oh    = 5

        ox = (w - ow) // 2
        oy = (h - oh) // 2

        self._overlay_box(oy, ox, oh, ow, title="Delete File?", danger=True)

        try:
            if is_second:
                self.scr.attron(curses.color_pair(7) | curses.A_BOLD)
                self.scr.addstr(oy + 1, ox + 2, trunc(warn, ow - 4))
                self.scr.attroff(curses.color_pair(7) | curses.A_BOLD)
                self.scr.addstr(oy + 2, ox + 2, trunc(msg, ow - 4))
                # Progress hint
                hint = f"Progress: {fmt_dur(pos)} / {fmt_dur(dur)}" if pos > 5 else "Never played"
                self.scr.attron(curses.color_pair(3))
                self.scr.addstr(oy + 3, ox + 2, hint)
                self.scr.attroff(curses.color_pair(3))
                brow = oy + 5
            else:
                self.scr.addstr(oy + 1, ox + 2, trunc(msg, ow - 4))
                brow = oy + 3
        except Exception:
            pass

        self._draw_badges_at(brow, ox + 2, [("y", "confirm"), ("Esc", "cancel")])

    def _draw_separator(self, y, w, label=""):
        line = "─" * w
        if label:
            mid  = (w - len(label)) // 2
            line = "─" * mid + label + "─" * (w - mid - len(label))
        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(y, 0, trunc(line, w))
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

    def _draw_content(self, top, height, w):
        if self.view == self.VIEW_PODCASTS:
            self._draw_list(top, height, w, self.podcasts, self.pod_cursor, self.pod_offset,
                            lambda _, p: (trunc(p.get("title", ""), w - 4), ""))

        elif self.view == self.VIEW_EPISODES:
            self._draw_list(top, height, w, self.episodes, self.ep_cursor, self.ep_offset,
                            lambda _, ep: (
                                self._ep_indicator(ep) + " " + trunc(ep.get("title", ""), w - 28),
                                self._ep_right(ep),
                            ))

        elif self.view == self.VIEW_QUEUE:
            self._draw_list(top, height, w, self.queue_items, self.q_cursor, self.q_offset,
                            lambda idx, ep: (
                                self._queue_left(idx, ep, w),
                                self._queue_right(ep),
                            ))

        elif self.view == self.VIEW_FILES:
            self._draw_list(top, height, w, self.files_items, self.f_cursor, self.f_offset,
                            lambda _, f: (
                                self._file_indicator(f) + " " + trunc(f.get("title", ""), w - 30),
                                self._file_right(f),
                            ))

        elif self.view == self.VIEW_DISCOVER:
            self._draw_discover(top, height, w)

    def _draw_list(self, top, height, w, items, cursor, offset, fmt):
        if not items:
            loading = "Loading" in self.status_msg or (
                self.view == self.VIEW_PODCASTS and not self.pods_loaded)
            msg = "Loading..." if loading else "No results."
            self.scr.attron(curses.color_pair(3))
            self.scr.addstr(top + 1, 2, msg)
            self.scr.attroff(curses.color_pair(3))
            return

        for i, item in enumerate(items[offset: offset + height]):
            y   = top + i
            idx = offset + i
            sel = idx == cursor

            left, right = fmt(idx, item)
            right_w = len(right)
            left_w  = w - right_w - 3
            left    = trunc(left, left_w)
            line    = f" {left:<{left_w}} {right} "

            try:
                if sel:
                    self.scr.attron(curses.A_REVERSE | curses.A_BOLD)
                    self.scr.addstr(y, 0, trunc(line, w))
                    self.scr.attroff(curses.A_REVERSE | curses.A_BOLD)
                else:
                    # Left text: use theme fg (pair 8)
                    self.scr.attron(curses.color_pair(8))
                    self.scr.addstr(y, 0, f" {left:<{left_w}} ")
                    self.scr.attroff(curses.color_pair(8))
                    # Right text: use theme info/yellow (pair 3) - dates, durations
                    if right:
                        self.scr.attron(curses.color_pair(3))
                        try:
                            self.scr.addstr(y, 1 + left_w + 1, f"{right} ")
                        except Exception:
                            pass
                        self.scr.attroff(curses.color_pair(3))
                    # Indicator override for episodes/files
                    if self.view in (self.VIEW_EPISODES, self.VIEW_FILES):
                        stat = item.get("playingStatus", 0) or 0
                        pos  = item.get("playedUpTo", 0) or 0
                        dur  = int(item.get("duration", 0) or 0)
                        if stat == 3 or (dur and int(pos) >= dur - 30):
                            col = curses.color_pair(2)
                        elif pos and int(pos) > 5:
                            col = curses.color_pair(3)
                        else:
                            col = curses.color_pair(8) | curses.A_DIM
                        self.scr.addstr(y, 1, left[0], col)
            except Exception:
                pass

        # Scrollbar
        if len(items) > height:
            bar_h   = max(1, height * height // len(items))
            bar_pos = int(height * offset / len(items))
            for y in range(height):
                char = "█" if bar_pos <= y < bar_pos + bar_h else "░"
                try:
                    self.scr.addstr(top + y, w - 1, char, curses.color_pair(3))
                except Exception:
                    pass

    def _queue_left(self, idx, ep, w):
        title = trunc(ep.get("title", ""), w - 32)
        if self.queue_mode == "up_next":
            return ("▶ " if idx == 0 else f"{idx}. ") + title
        return title

    def _queue_right(self, ep):
        pod = ep.get("podcastTitle", "")
        if ep.get("duration"):
            return (f"{trunc(pod, 14)}  "
                    f"{fmt_dur(ep.get('playedUpTo', 0))}/{fmt_dur(ep.get('duration', 0))}")
        return trunc(pod, 26)

    def _ep_indicator(self, ep):
        stat = ep.get("playingStatus", 0) or 0
        pos  = ep.get("playedUpTo", 0) or 0
        if stat == 3:          return "●"
        elif pos and int(pos) > 5: return "◐"
        return "○"

    def _file_indicator(self, f):
        dur  = int(f.get("duration", 0) or 0)
        pos  = int(f.get("playedUpTo", 0) or 0)
        stat = int(f.get("playingStatus", 0) or 0)
        if stat == 3 or (dur and pos >= dur - 30): return "●"
        elif pos > 5:                               return "◐"
        return "○"

    def _ep_right(self, ep):
        pos  = ep.get("playedUpTo", 0) or 0
        dur  = ep.get("duration", 0) or 0
        date = fmt_date(ep.get("publishedAt", ""))
        base = f"{fmt_dur(dur)}  {date}"
        return f"{fmt_dur(pos)}/{base}" if pos and int(pos) > 5 else base

    def _file_right(self, f):
        pos  = int(f.get("playedUpTo", 0) or 0)
        dur  = int(f.get("duration", 0) or 0)
        date = fmt_date(f.get("published", f.get("modifiedAt", "")))
        base = f"{fmt_dur(dur)}  {date}"
        return f"{fmt_dur(pos)}/{base}" if pos > 5 else base

    # ── Discover view ──

    def _draw_discover(self, top, height, w):
        list_top = top + 2
        list_h   = height - 2

        if self.discover_searching:
            # Show search input
            query_str = self.discover_query + "█"
            self.scr.attron(curses.color_pair(1) | curses.A_BOLD)
            try:
                self.scr.addstr(top, 2, "Search:")
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(1) | curses.A_BOLD)
            self.scr.attron(curses.color_pair(2))
            try:
                self.scr.addstr(top, 10, trunc(f"> {query_str}", w - 14))
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(2))
        else:
            # Sub-mode bar: Trending / Popular / Featured
            x = 2
            for i, (mode, label) in enumerate(DISCOVER_MODES):
                is_active  = mode == self.discover_list_mode
                is_focused = (self.focus_level == self.FOCUS_SUBMENU
                              and i == self.discover_mode_cursor)

                if is_focused:
                    self.scr.attron(curses.A_REVERSE | curses.A_BOLD)
                elif is_active:
                    self.scr.attron(curses.color_pair(2) | curses.A_BOLD)
                else:
                    self.scr.attron(curses.color_pair(3))

                try:
                    self.scr.addstr(top, x, label)
                except Exception:
                    pass

                if is_focused:
                    self.scr.attroff(curses.A_REVERSE | curses.A_BOLD)
                elif is_active:
                    self.scr.attroff(curses.color_pair(2) | curses.A_BOLD)
                else:
                    self.scr.attroff(curses.color_pair(3))

                x += len(label) + 3

            self.scr.attron(curses.color_pair(3))
            try:
                hint = "Tab=nav  / search"
                self.scr.addstr(top, w - len(hint) - 2, hint)
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(3))

        self._draw_separator(top + 1, w)

        if not self.discover_results:
            hint = "No results." if self.discover_query else "Loading..."
            self.scr.attron(curses.color_pair(3))
            try:
                self.scr.addstr(list_top + 1, 2, hint)
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(3))
            return

        for i, pod in enumerate(self.discover_results[self.discover_offset: self.discover_offset + list_h]):
            idx       = self.discover_offset + i
            sel       = idx == self.discover_cursor
            already   = pod.get("uuid", "") in self.subscribed_uuids
            indicator = "✓" if already else "+"
            col_ind   = curses.color_pair(2) if already else curses.color_pair(1)
            title     = trunc(pod.get("title", ""), w - 24)
            author    = trunc(pod.get("author", ""), 18)
            line      = f"  {indicator} {title:<{w - 26}} {author}"
            try:
                if sel:
                    self.scr.attron(curses.A_REVERSE | curses.A_BOLD)
                    self.scr.addstr(list_top + i, 0, trunc(line, w))
                    self.scr.attroff(curses.A_REVERSE | curses.A_BOLD)
                else:
                    # Title in theme fg
                    self.scr.attron(curses.color_pair(8))
                    self.scr.addstr(list_top + i, 0, trunc(line, w))
                    self.scr.attroff(curses.color_pair(8))
                    # Author in info color
                    self.scr.attron(curses.color_pair(3))
                    try:
                        self.scr.addstr(list_top + i, w - len(author) - 1, author)
                    except Exception:
                        pass
                    self.scr.attroff(curses.color_pair(3))
                    # Indicator in semantic color
                    self.scr.attron(col_ind | curses.A_BOLD)
                    self.scr.addstr(list_top + i, 2, indicator)
                    self.scr.attroff(col_ind | curses.A_BOLD)
            except Exception:
                pass

        if len(self.discover_results) > list_h:
            bar_h   = max(1, list_h * list_h // len(self.discover_results))
            bar_pos = int(list_h * self.discover_offset / len(self.discover_results))
            for y in range(list_h):
                char = "█" if bar_pos <= y < bar_pos + bar_h else "░"
                try:
                    self.scr.addstr(list_top + y, w - 1, char, curses.color_pair(3))
                except Exception:
                    pass

    # ── Player panel ──

    def _draw_player(self, top, w):
        pos  = self.mpv.get_position() if self.mpv.is_running() else 0
        dur  = self.mpv.get_duration() if self.mpv.is_running() else 0
        paus = self.mpv.get_paused()   if self.mpv.is_running() else True
        spd  = SPEEDS[self.speed_idx]

        ep_title  = self.playing_ep.get("title", "")  if self.playing_ep  else ""
        pod_title = self.playing_pod.get("title", "") if self.playing_pod else ""

        # Chapter info (refreshed about once a second by MPV.poll)
        chapter_name = ""
        if self.mpv.is_running():
            ch_idx  = self.mpv.get_chapter()
            ch_list = self.mpv.get_chapter_list()
            if ch_list and 0 <= ch_idx < len(ch_list):
                chapter_name = ch_list[ch_idx].get("title", "")

        # Line 1: podcast / episode titles (chapter overrides if available)
        if chapter_name:
            self.scr.attron(curses.color_pair(8))
            try:
                self.scr.addstr(top, 1, trunc(f"  § {chapter_name}", w - 2))
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(8))
        else:
            self.scr.attron(curses.color_pair(1))
            self.scr.addstr(top, 1, trunc(f"♫  {pod_title}", w // 2))
            self.scr.attroff(curses.color_pair(1))
            self.scr.attron(curses.color_pair(4))
            try:
                self.scr.addstr(top, w // 2, trunc(ep_title, w - w // 2 - 1))
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(4))

        # Line 2: progress bar or paused indicator
        times   = f" {fmt_dur(pos)} / {fmt_dur(dur)} "
        spd_str = f" {spd}x"
        if not self.mpv.is_running() and self.playing_ep:
            saved = int(self.playing_ep.get("playedUpTo", 0) or 0)
            self.scr.attron(curses.color_pair(2) | curses.A_BOLD)
            try:
                self.scr.addstr(top + 1, 0, f" ▶ {fmt_dur(saved)} / {fmt_dur(int(self.playing_ep.get('duration', 0) or 0))}")
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(2) | curses.A_BOLD)
            self.scr.attron(curses.color_pair(3))
            try:
                hint = "  loading..." if self.loading_stream else "  press space to continue"
                self.scr.addstr(top + 1, 18, hint)
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(3))
        else:
            state = "⏸" if paus else "▶"
            bar_w  = w - len(times) - len(spd_str) - 5
            filled = int(bar_w * pos / dur) if dur else 0
            bar    = "━" * filled + "─" * max(0, bar_w - filled)

            self.scr.attron(curses.color_pair(2) | curses.A_BOLD)
            self.scr.addstr(top + 1, 0, f" {state} {times}")
            self.scr.attroff(curses.color_pair(2) | curses.A_BOLD)
            self.scr.attron(curses.color_pair(3))
            try:
                self.scr.addstr(top + 1, 4 + len(times), f"[{bar}]")
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(3))
            self.scr.attron(curses.color_pair(2))
            try:
                self.scr.addstr(top + 1, 4 + len(times) + len(bar) + 2, spd_str)
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(2))

        # Line 3: progress % + skip silence label
        pct      = int(pos / dur * 100) if dur else 0
        ss_label = ["", "normal", "medium", "aggressive"][self.skip_silence]
        ss_str   = f"  skip:{ss_label}" if self.skip_silence else ""
        pct_str = f"{pct}% completed{ss_str}"
        if self.sleep_timer_end:
            remaining = max(0, int(self.sleep_timer_end - time.time()))
            tm, ts    = divmod(remaining, 60)
            sleep_str = f"Sleep: {tm}:{ts:02d}"
            padding   = max(0, w - len(pct_str) - len(sleep_str) - 2)
            line3     = f" {pct_str}{' ' * padding}{sleep_str}"
        else:
            line3 = f" {pct_str}"
        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(top + 2, 0, trunc(line3, w))
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

        # Line 4: key badges
        self._draw_badges(top + 3, w, [
            (row.blabel, row.pbadge) for row in KEYMAP if row.pbadge
        ])

    # ── Footer ──

    def _draw_footer(self, y, w):
        msg   = self.status_msg
        color = curses.color_pair(7) if self.status_error else curses.color_pair(3)

        # Auto-clear status after 4s
        if msg and time.time() - self.status_timer > 4:
            self.status_msg   = ""
            self.status_error = False
            msg = ""

        if msg:
            try:
                self.scr.attron(color)
                self.scr.addstr(y, 0, trunc(f" {msg}", w))
                self.scr.attroff(color)
            except Exception:
                pass
            return

        if self.mpv.is_running() or self.playing_ep:
            return

        self._draw_badges(y, w, [
            (row.blabel, row.badge) for row in KEYMAP
            if row.badge and (row.badge_views is None or self._ctx() in row.badge_views)
        ])

    def _draw_badges(self, y, w, badges):
        x = 1
        for label, desc in badges:
            if x >= w - 2:
                break
            try:
                self.scr.attron(curses.A_REVERSE | curses.A_BOLD)
                self.scr.addstr(y, x, f" {label} ")
                self.scr.attroff(curses.A_REVERSE | curses.A_BOLD)
                x += len(label) + 2
                self.scr.attron(curses.color_pair(3))
                self.scr.addstr(y, x, f"{desc} ")
                self.scr.attroff(curses.color_pair(3))
                x += len(desc) + 2
            except Exception:
                pass

    # ── Overlays ──

    def _overlay_box(self, oy, ox, oh, ow, title="", danger=False):
        """Draw a bordered box. Returns inner area coords."""
        pair = curses.color_pair(7) if danger else curses.color_pair(1)
        for y in range(oh):
            try:
                if y == 0 or y == oh - 1:
                    self.scr.attron(pair)
                    self.scr.addstr(oy + y, ox, "─" * ow)
                    self.scr.attroff(pair)
                else:
                    self.scr.addstr(oy + y, ox, "│" + " " * (ow - 2) + "│")
            except Exception:
                pass
        if title:
            self.scr.attron(pair | curses.A_BOLD)
            try:
                self.scr.addstr(oy, ox + 2, f"┤ {title} ├")
            except Exception:
                pass
            self.scr.attroff(pair | curses.A_BOLD)

    def _draw_search_overlay(self):
        if not self.searching:
            return
        h, w = self.scr.getmaxyx()
        ow = min(w - 4, 80)
        oh = min(h - 4, 24)
        ox = (w - ow) // 2
        oy = (h - oh) // 2

        for y in range(oh):
            try:
                self.scr.attron(curses.color_pair(4))
                self.scr.addstr(oy + y, ox, " " * ow)
                self.scr.attroff(curses.color_pair(4))
            except Exception:
                pass

        is_ep  = self.view == self.VIEW_EPISODES
        label  = "Search episodes:" if is_ep else "Search podcasts:"
        self.scr.attron(curses.color_pair(1) | curses.A_BOLD)
        try:
            self.scr.addstr(oy, ox + 2, f" {label} ")
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(1) | curses.A_BOLD)

        self.scr.attron(curses.color_pair(2))
        try:
            self.scr.addstr(oy + 1, ox + 2, trunc(f"> {self.search_query}█", ow - 4))
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(2))

        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(oy + 2, ox + 2, "─" * (ow - 4))
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

        items  = self.search_results if is_ep else self.pod_search_results
        cursor = self.search_cursor  if is_ep else self.pod_search_cursor
        offset = self.search_offset  if is_ep else self.pod_search_offset

        if not items:
            hint = "No results." if len(self.search_query) > 1 else "Type to search..."
            self.scr.attron(curses.color_pair(3))
            try:
                self.scr.addstr(oy + 3, ox + 2, hint)
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(3))
        else:
            max_rows = oh - 5
            for i, item in enumerate(items[offset: offset + max_rows]):
                idx = offset + i
                sel = idx == cursor
                if is_ep:
                    left  = trunc(item.get("title", ""), ow - 16)
                    right = fmt_dur(item.get("duration", 0))
                else:
                    left  = trunc(item.get("title", ""), ow - 20)
                    right = trunc(item.get("author", ""), 16)
                line = f" {left:<{ow - len(right) - 5}} {right} "
                try:
                    if sel:
                        self.scr.attron(curses.A_REVERSE | curses.A_BOLD)
                        self.scr.addstr(oy + 3 + i, ox, trunc(line, ow))
                        self.scr.attroff(curses.A_REVERSE | curses.A_BOLD)
                    else:
                        self.scr.addstr(oy + 3 + i, ox, trunc(line, ow))
                except Exception:
                    pass

        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(oy + oh - 1, ox + 2, "Enter=select  Esc=close")
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

    def _draw_badges_at(self, y, x, badges):
        """Draw badges starting at a specific x position (for overlays)."""
        for label, desc in badges:
            try:
                self.scr.attron(curses.A_REVERSE | curses.A_BOLD)
                self.scr.addstr(y, x, f" {label} ")
                self.scr.attroff(curses.A_REVERSE | curses.A_BOLD)
                x += len(label) + 2
                self.scr.attron(curses.color_pair(3))
                self.scr.addstr(y, x, f"{desc} ")
                self.scr.attroff(curses.color_pair(3))
                x += len(desc) + 2
            except Exception:
                pass

    def _draw_desc_overlay(self):
        if not self.show_desc:
            return
        ep = None
        if self.view == self.VIEW_EPISODES and self.episodes:
            ep = self.episodes[self.ep_cursor]
        elif self.view == self.VIEW_QUEUE and self.queue_items:
            ep = self.queue_items[self.q_cursor]
        if not ep:
            return

        h, w = self.scr.getmaxyx()
        ow = min(w - 6, 76)
        oh = min(h - 6, 22)
        ox = (w - ow) // 2
        oy = (h - oh) // 2

        self._overlay_box(oy, ox, oh, ow, title=trunc(ep.get("title", ""), ow - 6))

        desc = ep.get("description", "No description available.")
        desc = re.sub(r"<[^>]+>", "", desc)
        desc = re.sub(r"https?://\S+", "", desc)
        desc = re.sub(r"\s+", " ", desc).strip()

        # Split into chapters at timestamp markers
        chunk_pat  = re.compile(r"\(?\d{1,2}:\d{2}(?::\d{2})?\)?")
        parts      = chunk_pat.split(desc)
        timestamps = chunk_pat.findall(desc)
        lines      = []

        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            if i > 0 and i - 1 < len(timestamps):
                lines.append("─" * (ow - 4))
                lines.append(f"▶ {timestamps[i - 1].strip('()')}")
            for word in part.split():
                if lines and not lines[-1].startswith("─") and not lines[-1].startswith("▶"):
                    if len(lines[-1]) + len(word) + 1 <= ow - 4:
                        lines[-1] += f" {word}"
                        continue
                lines.append(word)

        if not lines:
            lines = ["No description available."]

        max_lines   = oh - 3
        desc_offset = getattr(self, "desc_offset", 0)

        for i, line in enumerate(lines[desc_offset: desc_offset + max_lines]):
            try:
                if line.startswith("─"):
                    self.scr.attron(curses.color_pair(3))
                    self.scr.addstr(oy + 1 + i, ox + 2, trunc(line, ow - 4))
                    self.scr.attroff(curses.color_pair(3))
                elif line.startswith("▶"):
                    self.scr.attron(curses.color_pair(2) | curses.A_BOLD)
                    self.scr.addstr(oy + 1 + i, ox + 2, trunc(line, ow - 4))
                    self.scr.attroff(curses.color_pair(2) | curses.A_BOLD)
                else:
                    self.scr.addstr(oy + 1 + i, ox + 2, trunc(line, ow - 4))
            except Exception:
                pass

        self.scr.attron(curses.color_pair(3))
        try:
            if len(lines) > max_lines:
                remaining  = len(lines) - desc_offset - max_lines
                scroll_hint = f"↓ {remaining} more" if remaining > 0 else "─ end ─"
                self.scr.addstr(oy + oh - 1, ox + ow - len(scroll_hint) - 4, scroll_hint)
            self.scr.addstr(oy + oh - 1, ox + 2, "┤ d / Esc = close ├")
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

    def _draw_theme_overlay(self):
        if not self.show_themes:
            return
        h, w = self.scr.getmaxyx()
        ow = min(w - 6, 40)
        oh = min(h - 2, len(self.THEMES) + 4)
        ox = (w - ow) // 2
        oy = max(1, (h - oh) // 2)

        self._overlay_box(oy, ox, oh, ow, title="Theme")

        # Show a window of the list that always contains the cursor
        rows  = max(1, oh - 4)
        first = max(0, min(self.theme_cursor - rows // 2, len(self.THEMES) - rows))
        for i, theme in enumerate(self.THEMES[first: first + rows]):
            sel    = first + i == self.theme_cursor
            active = first + i == self.current_theme
            bullet = "●" if active else "○"
            try:
                if sel:
                    self.scr.attron(curses.A_REVERSE | curses.A_BOLD)
                    self.scr.addstr(oy + 1 + i, ox + 2, f"  {bullet} {theme['name']:<24}")
                    self.scr.attroff(curses.A_REVERSE | curses.A_BOLD)
                else:
                    col = curses.color_pair(2) if active else curses.color_pair(4)
                    self.scr.attron(col)
                    self.scr.addstr(oy + 1 + i, ox + 2, f"  {bullet} {theme['name']:<24}")
                    self.scr.attroff(col)
            except Exception:
                pass

        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(oy + oh - 1, ox + 2, "┤ Enter=apply  Esc=close ├")
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

    def _draw_keymap_overlay(self):
        if not self.show_keys:
            return
        h, w = self.scr.getmaxyx()

        # (key label, description); description None marks a section heading
        lines = []
        for section in (SEC_NAV, SEC_PLAYER, SEC_OTHER):
            if lines:
                lines.append(("", None))
            lines.append((section, None))
            lines += [(r.label, r.desc) for r in KEYMAP if r.help and r.section == section]

        ow = min(w - 6, 72)
        oh = min(h - 2, len(lines) + 2)
        ox = (w - ow) // 2
        oy = max(1, (h - oh) // 2)
        max_lines        = max(1, oh - 2)
        self.keys_offset = max(0, min(self.keys_offset, len(lines) - max_lines))

        self._overlay_box(oy, ox, oh, ow, title="Keymap")

        for i, (key, action) in enumerate(lines[self.keys_offset: self.keys_offset + max_lines]):
            try:
                if action is None:
                    self.scr.attron(curses.color_pair(2) | curses.A_BOLD)
                    self.scr.addstr(oy + 1 + i, ox + 2, key)
                    self.scr.attroff(curses.color_pair(2) | curses.A_BOLD)
                else:
                    self.scr.attron(curses.color_pair(3))
                    self.scr.addstr(oy + 1 + i, ox + 4, f"{key:<16}")
                    self.scr.attroff(curses.color_pair(3))
                    self.scr.addstr(oy + 1 + i, ox + 21, trunc(action, ow - 23))
            except Exception:
                pass

        self.scr.attron(curses.color_pair(3))
        try:
            more = len(lines) - self.keys_offset - max_lines
            if more > 0:
                hint = f"↓ {more} more"
                self.scr.addstr(oy + oh - 1, ox + ow - len(hint) - 4, hint)
            self.scr.addstr(oy + oh - 1, ox + 2, "┤ ↑↓=scroll  ? / Esc = close ├")
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

    def _sleep_options(self):
        """Return current sleep timer options list as (label, minutes)."""
        opts = [
            ("5 minutes",  5),
            ("15 minutes", 15),
            ("30 minutes", 30),
            ("60 minutes", 60),
        ]
        if self.sleep_timer_end:
            remaining = max(0, int(self.sleep_timer_end - time.time()))
            m, s = divmod(remaining, 60)
            opts.insert(0, (f"Cancel timer ({m}:{s:02d} left)", -1))
        return opts

    def _draw_sleep_menu_overlay(self):
        if not self.show_sleep_menu:
            return
        h, w    = self.scr.getmaxyx()
        options = self._sleep_options()
        ow      = 34
        oh      = len(options) + 4
        ox      = (w - ow) // 2
        oy      = (h - oh) // 2

        self._overlay_box(oy, ox, oh, ow, title="Sleep Timer")

        for i, (label, _) in enumerate(options):
            sel = i == self.sleep_cursor
            try:
                if sel:
                    self.scr.attron(curses.A_REVERSE | curses.A_BOLD)
                    self.scr.addstr(oy + 1 + i, ox + 2, f"  {label:<26}")
                    self.scr.attroff(curses.A_REVERSE | curses.A_BOLD)
                else:
                    self.scr.attron(curses.color_pair(3))
                    self.scr.addstr(oy + 1 + i, ox + 2, f"  {label:<26}")
                    self.scr.attroff(curses.color_pair(3))
            except Exception:
                pass

        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(oy + oh - 1, ox + 2, "┤ ↑↓=nav  Enter=select  Esc=close ├")
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

    def _draw_unsub_confirm_overlay(self):
        if not self.unsub_confirm or not self.unsub_target:
            return
        h, w  = self.scr.getmaxyx()
        title = self.unsub_target.get("title", "this podcast")
        msg   = f"Unsubscribe from: {trunc(title, 40)}?"
        ow    = max(len(msg) + 8, 52)
        oh    = 5
        ox    = (w - ow) // 2
        oy    = (h - oh) // 2

        self._overlay_box(oy, ox, oh, ow, title="Unsubscribe?", danger=True)
        try:
            self.scr.addstr(oy + 1, ox + 2, trunc(msg, ow - 4))
        except Exception:
            pass
        self._draw_badges_at(oy + 3, ox + 2, [("y", "confirm"), ("Esc", "cancel")])

    # ─────────────────────────────────────────
    # Input handling
    # ─────────────────────────────────────────

    def _top_overlay(self):
        """The open overlay that owns the keyboard, or None."""
        for ov in OVERLAYS:
            if ov.is_open(self):
                return ov
        return None

    def handle_key(self, key):
        """Route one key press. Returns False when the app should quit."""
        top = self._top_overlay()

        # ── q: close what is open, then quit (a text field types the letter) ──
        if key in (ord("q"), ord("Q")) and not (top and top.text):
            if top:
                getattr(self, top.close)()
            elif self.focus_level != self.FOCUS_CONTENT:
                self.focus_level = self.FOCUS_CONTENT
            else:
                return False
            return True

        # ── Esc: close what is open, then step back ──
        if key == 27:
            if top:
                getattr(self, top.close)()
            elif self.focus_level != self.FOCUS_CONTENT:
                self.focus_level = self.FOCUS_CONTENT
            elif self.view == self.VIEW_EPISODES:
                self.view = self.VIEW_PODCASTS
            return True

        # ── An open overlay takes every other key ──
        if top:
            getattr(self, top.key)(key)
            return True

        # ── Tab / Shift+Tab: cycle focus ──
        if key == 9:
            self._focus_next()
            return True
        if key == curses.KEY_BTAB:
            self._focus_prev()
            return True

        # ── Focus-aware navigation ──
        if self.focus_level == self.FOCUS_TABBAR:
            if key in (curses.KEY_RIGHT, ord("l")):
                self.tab_cursor = (self.tab_cursor + 1) % len(TABS)
            elif key in (curses.KEY_LEFT, ord("h")):
                self.tab_cursor = (self.tab_cursor - 1) % len(TABS)
            elif key in _ENTER:
                self._activate_tab(self.tab_cursor)
            return True

        if self.focus_level == self.FOCUS_SUBMENU and self.view == self.VIEW_DISCOVER:
            if key in (curses.KEY_RIGHT, ord("l")):
                self.discover_mode_cursor = (self.discover_mode_cursor + 1) % len(DISCOVER_MODES)
            elif key in (curses.KEY_LEFT, ord("h")):
                self.discover_mode_cursor = (self.discover_mode_cursor - 1) % len(DISCOVER_MODES)
            elif key in _ENTER:
                mode = DISCOVER_MODES[self.discover_mode_cursor][0]
                self.discover_query = ""
                self.load_discover_list(mode)
                self.focus_level = self.FOCUS_CONTENT
            return True

        # ── Everything else comes from the key registry ──
        self._dispatch(key)
        return True

    def _ctx(self):
        """The view name the key registry sees. The Up Next tab shares the
        queue view but has its own keys, so it reports as "upnext"."""
        if self.view == self.VIEW_QUEUE and self.queue_mode == "up_next":
            return "upnext"
        return self.view

    def _dispatch(self, key):
        """Run the registry action bound to key in the current view, if any."""
        ctx = self._ctx()
        for row in KEYMAP:
            if row.views is not None and ctx not in row.views:
                continue
            if row.needs == "mpv" and not self.mpv.is_running():
                continue
            for codes, action, arg in row.binds:
                if key in codes:
                    handler = getattr(self, f"_act_{action}")
                    if arg is None:
                        handler()
                    else:
                        handler(arg)
                    return True
        return False

    # ── Registry actions: lists ──

    def _nav_list(self):
        """(items, cursor attribute, offset attribute, visible rows) of the current view."""
        vis = max(1, self._visible_rows())
        if self.view == self.VIEW_PODCASTS:
            return self.podcasts, "pod_cursor", "pod_offset", vis
        if self.view == self.VIEW_EPISODES:
            return self.episodes, "ep_cursor", "ep_offset", vis
        if self.view == self.VIEW_QUEUE:
            return self.queue_items, "q_cursor", "q_offset", vis
        if self.view == self.VIEW_FILES:
            return self.files_items, "f_cursor", "f_offset", vis
        return self.discover_results, "discover_cursor", "discover_offset", max(1, vis - 2)

    def _move_cursor(self, delta):
        items, cur, off, vis = self._nav_list()
        c, o = self._scroll(getattr(self, cur), getattr(self, off), delta, len(items), vis)
        setattr(self, cur, c)
        setattr(self, off, o)

    def _selected(self):
        items, cur, _, _ = self._nav_list()
        idx = getattr(self, cur)
        return items[idx] if 0 <= idx < len(items) else None

    def _act_move(self, delta):
        self._move_cursor(delta)

    def _act_page(self, direction):
        self._move_cursor(direction * self._nav_list()[3])

    def _act_edge(self, direction):
        self._move_cursor(direction * max(1, len(self._nav_list()[0])))

    def _act_tab(self, idx):
        self._activate_tab(idx)

    def _act_select(self):
        item = self._selected()
        if item is None:
            return
        if self.view == self.VIEW_PODCASTS:
            self.load_episodes(item)
        elif self.view == self.VIEW_EPISODES:
            self.play(self.current_pod, item)
        elif self.view == self.VIEW_QUEUE:
            if item.get("file"):
                self.play_file(item["file"])   # an uploaded file sitting in Up Next
                return
            pod_uuid = item.get("podcastUuid") or item.get("podcast_uuid") or item.get("podcast")
            self.play({"uuid": pod_uuid, "title": item.get("podcastTitle", "")}, item)
        elif self.view == self.VIEW_FILES:
            self.play_file(item)
        elif self.view == self.VIEW_DISCOVER:
            self._do_subscribe(item)

    def _act_back(self):
        self.view = self.VIEW_PODCASTS

    def _act_search(self):
        if self.view == self.VIEW_DISCOVER:
            self.discover_searching = True
            return
        self.searching          = True
        self.search_query       = ""
        self.search_results     = []
        self.pod_search_results = []
        self.search_cursor      = self.search_offset     = 0
        self.pod_search_cursor  = self.pod_search_offset = 0

    def _act_describe(self):
        if self._selected() is not None:
            self.show_desc   = True
            self.desc_offset = 0

    def _act_unsubscribe(self):
        pod = self._selected()
        if pod is not None:
            self.unsub_target  = pod
            self.unsub_confirm = True

    def _act_delete_file(self):
        f = self._selected()
        if f is not None:
            self.del_file_target = f
            self.del_file_step   = 1

    def _item_podcast_uuid(self, item):
        if self.view == self.VIEW_EPISODES:
            return (self.current_pod or {}).get("uuid", "")
        return item.get("podcastUuid") or item.get("podcast_uuid") or item.get("podcast") or ""

    def _act_queue_add(self, where):
        item = self._selected()
        if item is None:
            return
        payload = self.api.up_next_episode(self._item_podcast_uuid(item), item)
        if not payload:
            self.status("Cannot add to Up Next: Pocket Casts does not list this episode", error=True)
            return
        title = item.get("title", "")[:40]
        def _add():
            err = self.api.up_next_add(where, payload)
            if err:
                self.status(f"Up Next failed: {err}", error=True)
            else:
                self.status(f"Up Next ({'next' if where == 'next' else 'last'}): {title}")
        threading.Thread(target=_add, daemon=True).start()

    def _act_queue_remove(self):
        item = self._selected()
        if item is None:
            return
        uuid, title = item.get("uuid", ""), item.get("title", "")[:40]
        def _remove():
            err = self.api.up_next_remove([uuid])
            if err:
                self.status(f"Up Next failed: {err}", error=True)
                return
            self.queue_items = [e for e in self.queue_items if e.get("uuid") != uuid]
            self.q_cursor    = min(self.q_cursor, max(0, len(self.queue_items) - 1))
            self.status(f"Removed from Up Next: {title}")
        threading.Thread(target=_remove, daemon=True).start()

    def _act_reload(self):
        if self.view == self.VIEW_PODCASTS:
            self.load_podcasts()
        elif self.view == self.VIEW_QUEUE:
            self.load_queue(keep_cursor=True)
        elif self.view == self.VIEW_FILES:
            self.load_files()

    # ── Registry actions: player ──

    def _act_toggle_play(self):
        if self.loading_stream:
            return
        if self.mpv.is_running():
            self.mpv.pause_toggle()
            if self.playing_pod and self.playing_ep:
                pos = self.mpv.get_position()
                self._remember_position(pos)
                self._push_sync(pos)
                self.last_sync = time.time()
        elif self.playing_ep:
            if self.playing_pod and self.playing_pod.get("uuid") == "__files__":
                self.play_file(self.playing_ep)
            else:
                self.play(self.playing_pod or {"uuid": "", "title": ""}, self.playing_ep)

    def _act_seek(self, secs):
        self.mpv.seek(secs)

    def _act_chapter(self, direction):
        if direction > 0:
            self.mpv.next_chapter()
        else:
            self.mpv.prev_chapter()

    def _act_speed(self, direction):
        self.speed_idx = max(0, min(len(SPEEDS) - 1, self.speed_idx + direction))
        if self.mpv.is_running():
            self.mpv.set_speed(SPEEDS[self.speed_idx])
        self.status(f"Speed: {SPEEDS[self.speed_idx]}x")
        self._save_prefs()

    def _act_cycle_silence(self):
        self.skip_silence = (self.skip_silence + 1) % 4
        if self.mpv.is_running():
            self.mpv.set_skip_silence(self.skip_silence)
        labels = ["off", "normal", "medium", "aggressive"]
        self.status(f"Skip silence: {labels[self.skip_silence]}")
        self._save_prefs()

    def _act_sleep_menu(self):
        self.show_sleep_menu = True
        self.sleep_cursor    = 0

    # ── Registry actions: other ──

    def _act_themes(self):
        self.show_themes  = True
        self.theme_cursor = self.current_theme

    def _act_keys(self):
        self.show_keys   = True
        self.keys_offset = 0

    def _save_prefs(self):
        save_prefs(self.THEMES[self.current_theme]["name"], self.speed_idx, self.skip_silence)

    # ── Overlay key handlers and closers ──

    def _close_delete(self):
        self.del_file_step   = 0
        self.del_file_target = None

    def _key_delete(self, key):
        if key not in (ord("y"), ord("Y")):
            self._close_delete()
        elif self.del_file_step == 1:
            f = self.del_file_target
            if is_played(f):
                self._do_delete_file()
            else:
                self.del_file_step = 2
        else:
            self._do_delete_file()

    def _close_unsub(self):
        self.unsub_confirm = False
        self.unsub_target  = None

    def _key_unsub(self, key):
        if key in (ord("y"), ord("Y")):
            self._do_unsubscribe()
        else:
            self._close_unsub()

    def _close_sleep(self):
        self.show_sleep_menu = False

    def _key_sleep(self, key):
        options = self._sleep_options()
        if key in (curses.KEY_DOWN, ord("j")):
            self.sleep_cursor = (self.sleep_cursor + 1) % len(options)
        elif key in (curses.KEY_UP, ord("k")):
            self.sleep_cursor = (self.sleep_cursor - 1) % len(options)
        elif key in _ENTER:
            _, mins = options[min(self.sleep_cursor, len(options) - 1)]
            if mins == -1:
                self.sleep_timer_end = 0
                self.status("Sleep timer cancelled.")
            else:
                self.sleep_timer_end = time.time() + mins * 60
                self.status(f"Sleep timer set: {mins} min")
            self.show_sleep_menu = False
        elif key == ord("z"):
            self.show_sleep_menu = False

    def _close_keys(self):
        self.show_keys = False

    def _key_keys(self, key):
        if key == ord("?"):
            self.show_keys = False
        elif key in (curses.KEY_DOWN, ord("j")):
            self.keys_offset += 1
        elif key in (curses.KEY_UP, ord("k")):
            self.keys_offset = max(0, self.keys_offset - 1)
        elif key == curses.KEY_NPAGE:
            self.keys_offset += 10
        elif key == curses.KEY_PPAGE:
            self.keys_offset = max(0, self.keys_offset - 10)

    def _close_themes(self):
        self.show_themes = False

    def _key_themes(self, key):
        if key in (curses.KEY_DOWN, ord("j")):
            self.theme_cursor = (self.theme_cursor + 1) % len(self.THEMES)
        elif key in (curses.KEY_UP, ord("k")):
            self.theme_cursor = (self.theme_cursor - 1) % len(self.THEMES)
        elif key in _ENTER:
            self.current_theme = self.theme_cursor
            self._apply_theme(self.current_theme)
            self.show_themes   = False
            self.status(f"Theme: {self.THEMES[self.current_theme]['name']}")
            self._save_prefs()
        elif key == ord("t"):
            self.show_themes = False

    def _close_search(self):
        self.searching    = False
        self.search_query = ""

    def _close_desc(self):
        self.show_desc = False

    def _key_desc(self, key):
        if key in (curses.KEY_DOWN, ord("j")):
            self.desc_offset += 1
        elif key in (curses.KEY_UP, ord("k")):
            self.desc_offset = max(0, self.desc_offset - 1)
        elif key == ord("d"):
            self.show_desc = False

    def _has_submenu(self):
        """True if current view has a sub-menu level."""
        return self.view == self.VIEW_DISCOVER

    def _focus_next(self):
        """Tab: advance focus level."""
        if self.focus_level == self.FOCUS_CONTENT:
            self.tab_cursor  = self._current_tab_idx()
            self.focus_level = self.FOCUS_TABBAR
        elif self.focus_level == self.FOCUS_TABBAR:
            if self._has_submenu():
                self.focus_level = self.FOCUS_SUBMENU
            else:
                self.focus_level = self.FOCUS_CONTENT
        elif self.focus_level == self.FOCUS_SUBMENU:
            self.focus_level = self.FOCUS_CONTENT

    def _focus_prev(self):
        """Shift+Tab: retreat focus level."""
        if self.focus_level == self.FOCUS_CONTENT:
            if self._has_submenu():
                self.focus_level = self.FOCUS_SUBMENU
            else:
                self.tab_cursor  = self._current_tab_idx()
                self.focus_level = self.FOCUS_TABBAR
        elif self.focus_level == self.FOCUS_TABBAR:
            self.focus_level = self.FOCUS_CONTENT
        elif self.focus_level == self.FOCUS_SUBMENU:
            self.tab_cursor  = self._current_tab_idx()
            self.focus_level = self.FOCUS_TABBAR

    def _close_discover_search(self):
        """Close discover search and restore curated list."""
        self.discover_searching = False
        self.discover_query     = ""
        m = self.discover_list_mode
        self.discover_results   = self.discover_lists.get(m, [])
        self.discover_cursor    = self.discover_offset = 0

    def _handle_search_key(self, key):
        is_ep = self.view == self.VIEW_EPISODES

        if key in (curses.KEY_BACKSPACE, 127):
            self.search_query = self.search_query[:-1]
            self._update_search_results()

        elif key in (curses.KEY_ENTER, 10, 13):
            items  = self.search_results if is_ep else self.pod_search_results
            cursor = self.search_cursor  if is_ep else self.pod_search_cursor
            if items:
                item = items[cursor]
                self.searching    = False
                self.search_query = ""
                if is_ep:
                    self.play(self.current_pod, item)
                else:
                    self._load_episodes_from_feed({
                        "uuid":    item.get("uuid", ""),
                        "title":   item.get("title", ""),
                        "feedUrl": item.get("feedUrl", ""),
                    })

        elif key == curses.KEY_DOWN:
            items = self.search_results if is_ep else self.pod_search_results
            vis   = min(self.scr.getmaxyx()[0] - 10, 18)
            if is_ep:
                self.search_cursor, self.search_offset = self._scroll(self.search_cursor, self.search_offset, 1, len(items), vis)
            else:
                self.pod_search_cursor, self.pod_search_offset = self._scroll(self.pod_search_cursor, self.pod_search_offset, 1, len(items), vis)

        elif key == curses.KEY_UP:
            items = self.search_results if is_ep else self.pod_search_results
            vis   = min(self.scr.getmaxyx()[0] - 10, 18)
            if is_ep:
                self.search_cursor, self.search_offset = self._scroll(self.search_cursor, self.search_offset, -1, len(items), vis)
            else:
                self.pod_search_cursor, self.pod_search_offset = self._scroll(self.pod_search_cursor, self.pod_search_offset, -1, len(items), vis)

        elif 32 <= key <= 126:
            self.search_query += chr(key)
            self._update_search_results()

        return True

    def _handle_discover_key(self, key):
        if key in (curses.KEY_BACKSPACE, 127):
            self.discover_query = self.discover_query[:-1]
            self._update_discover_results()
        elif key in _ENTER:
            if self.discover_results:
                self._do_subscribe(self.discover_results[self.discover_cursor])
            self.discover_searching = False
        elif key == curses.KEY_DOWN:
            vis = max(1, self.scr.getmaxyx()[0] - 8)
            self.discover_cursor, self.discover_offset = self._scroll(self.discover_cursor, self.discover_offset, 1, len(self.discover_results), vis - 2)
        elif key == curses.KEY_UP:
            vis = max(1, self.scr.getmaxyx()[0] - 8)
            self.discover_cursor, self.discover_offset = self._scroll(self.discover_cursor, self.discover_offset, -1, len(self.discover_results), vis - 2)
        elif 32 <= key <= 126:
            self.discover_query += chr(key)
            self._update_discover_results()

    # ─────────────────────────────────────────
    # Navigation helpers
    # ─────────────────────────────────────────

    def _scroll(self, cursor, offset, delta, total, visible):
        if total == 0:
            return 0, 0
        cursor = max(0, min(total - 1, cursor + delta))
        if cursor < offset:
            offset = cursor
        elif cursor >= offset + visible:
            offset = cursor - visible + 1
        return cursor, offset

    def _visible_rows(self):
        h, _ = self.scr.getmaxyx()
        # Layout: row 0=header, 1=tabs, 2=separator → content starts at 3
        # Footer: 1 row always
        # Player: separator(1) + player(4) + footer already counted = 5 extra
        # Matches draw(): player_h=6 includes separator, player draws at h-player_h
        # content_h = h - 3 - player_h - 1
        player_h = 6 if (self.mpv.is_running() or self.playing_ep) else 0
        return h - 3 - player_h - 1

    # ─────────────────────────────────────────
    # Startup: resume last played
    # ─────────────────────────────────────────

    def _load_last_played(self):
        """On startup, set playing_ep to the most recently played item.
        Runs in the background so the first screen appears right away."""
        def _load():
            try:
                in_prog  = self.api.in_progress()
                last_ep  = in_prog[0] if in_prog else None

                files = self.api.files()
                files.sort(key=lambda f: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', f.get('title', ''))])
                self.files_items = files

                with_progress = [f for f in files if (f.get("playedUpTo") or 0) > 5]
                last_file = sorted(with_progress, key=lambda f: f.get("modifiedAt", ""), reverse=True)
                last_file = last_file[0] if last_file else None

                def ts(x):
                    if not x:
                        return 0
                    mod = x.get("modifiedAt") or x.get("playedUpToModified", "0")
                    try:
                        if mod and "T" in str(mod):
                            return datetime.fromisoformat(mod.replace("Z", "+00:00")).timestamp()
                        if mod and mod != "0":
                            return int(mod) / 1000
                    except Exception:
                        pass
                    return 0

                ep_ts   = ts(last_ep)
                file_ts = ts(last_file)

                if last_ep and last_file:
                    recent = last_file if (ep_ts == 0 and file_ts > 0) or file_ts > ep_ts else last_ep
                else:
                    recent = last_ep or last_file

                if not recent or self.playing_ep or self.loading_stream:
                    return  # nothing to resume, or the user already started something

                file_uuids = {f.get("uuid") for f in files}
                if recent.get("uuid") in file_uuids:
                    self.playing_pod = {"uuid": "__files__", "title": "Files"}
                else:
                    self.playing_pod = {
                        "uuid":  recent.get("podcastUuid") or recent.get("podcast_uuid") or recent.get("podcast", ""),
                        "title": recent.get("podcastTitle", ""),
                    }
                self.playing_ep = recent
                self.status(f"Last played: {recent.get('title', '')[:50]}")
            except Exception as e:
                self.status(f"Resume error: {e}", error=True)

        threading.Thread(target=_load, daemon=True).start()

    # ─────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────

    def run(self):
        self.load_podcasts()
        self._load_last_played()

        while True:
            self.mpv.poll()
            self.draw()
            self.sync_position()
            self.check_finished()
            self.check_sleep_timer()

            self.scr.timeout(100)
            key = self.scr.getch()
            if key != -1 and not self.handle_key(key):
                break

        self.shutdown()

    def shutdown(self):
        """Final sync on exit. Waits for it, or the process would end first."""
        self._play_gen += 1
        if self.mpv.is_running():
            pos = self.mpv.get_position()
            self.mpv.quit()
            self._push_sync(pos, wait=True)
        else:
            self.mpv.quit()
        self._save_prefs()


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main(stdscr):
    token = load_token()
    if not token:
        token, err = curses_login(stdscr)
        if not token:
            try:
                curses.endwin()
            except Exception:
                pass
            print(f"Login error: {err}")
            sys.exit(1)
    api = API(token)
    tui = PocketTUI(stdscr, api)
    try:
        tui.run()
    except KeyboardInterrupt:
        tui.shutdown()


USAGE = f"""pocketcli {VERSION} - terminal client for Pocket Casts

Usage: pocketcli [option]

  (no option)   start the player
  --keys        print the keymap as Markdown
  --logout      forget the saved login
  --version     print the version
  --help        show this help
"""


def cli(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        opt = args[0]
        if opt in ("--version", "-V"):
            print(f"pocketcli {VERSION} ({BUILD})")
        elif opt in ("--help", "-h"):
            print(USAGE, end="")
        elif opt == "--keys":
            print(keymap_markdown())
        elif opt == "--logout":
            try:
                CONFIG_FILE.unlink()
                print("Logged out.")
            except FileNotFoundError:
                print("Not logged in.")
        else:
            print(f"pocketcli: unknown option {opt}\n\n{USAGE}", end="", file=sys.stderr)
            return 2
        return 0

    # Without this curses waits a full second after Esc before reporting it
    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(cli())
