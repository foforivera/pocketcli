#!/usr/bin/env python3
"""
pocketcli - Terminal client for Pocket Casts
Browse podcasts, play episodes, sync progress bidirectionally.
"""

VERSION = "1.8.0"
BUILD   = "2026-06-09"

import os
import re
import sys
import json
import time
import socket
import curses
import subprocess
import configparser
import threading
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
SOCKET_PATH = "/tmp/pocketcli-mpv.sock"
BASE_URL    = "https://api.pocketcasts.com"
ITUNES_URL  = "https://itunes.apple.com/search"
LISTS_URL   = "https://lists.pocketcasts.com"

# Tab definitions: (key, label, view, queue_mode)
TABS = [
    ("1", "Podcasts",    "podcasts",  None),
    ("2", "In Progress", "queue",     "in_progress"),
    ("3", "New",         "queue",     "new"),
    ("4", "Starred",     "queue",     "starred"),
    ("5", "Files",       "files",     None),
    ("6", "Discover",    "discover",  None),
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
    1: "lavfi=[silenceremove=start_periods=1:start_silence=0.5:start_threshold=-40dB:stop_periods=1:stop_silence=0.5:stop_threshold=-40dB]",
    2: "lavfi=[silenceremove=start_periods=1:start_silence=0.3:start_threshold=-35dB:stop_periods=1:stop_silence=0.3:stop_threshold=-35dB]",
    3: "lavfi=[silenceremove=start_periods=1:start_silence=0.15:start_threshold=-30dB:stop_periods=1:stop_silence=0.15:stop_threshold=-30dB]",
}

# ─────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────

def load_token():
    cfg = configparser.ConfigParser()
    if CONFIG_FILE.exists():
        cfg.read(CONFIG_FILE)
        return cfg.get("auth", "token", fallback=None)
    return None


def save_config(email, token, uuid):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    cfg["auth"] = {"email": email, "token": token, "uuid": uuid}
    with open(CONFIG_FILE, "w") as f:
        cfg.write(f)


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

class API:
    def __init__(self, token):
        self.token  = token
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        # Separate client for external APIs (no auth headers)
        self._ext = httpx.Client(timeout=10)

    # ── Internal helpers ──

    def _post(self, path, data=None):
        r = self.client.post(f"{BASE_URL}{path}", json=data or {})
        r.raise_for_status()
        return r.json()

    def _get(self, path):
        r = self.client.get(f"{BASE_URL}{path}")
        r.raise_for_status()
        return r.json()

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
            if results:
                return results[0].get("feedUrl")
        except Exception:
            pass
        return None

    def podcast_episodes_from_rss(self, feed_url, sync_data=None):
        """Parse an RSS feed and return episode dicts, merged with sync data."""
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "pocketcli/1.0"})
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

    def podcast_episodes(self, podcast_uuid, podcast_title="", feed_url=None):
        """Fetch episodes via RSS, falling back to PC API if unavailable."""
        if not feed_url:
            feed_url = self.podcast_feed_url(podcast_title)
        if not feed_url:
            return self._post("/user/podcast/episodes", {
                "uuid": podcast_uuid, "page": 0, "sort": 3,
            }).get("episodes", [])

        episodes = self.podcast_episodes_from_rss(feed_url)

        # Merge in-progress data by title match
        try:
            in_prog       = self._post("/user/in_progress").get("episodes", [])
            prog_by_title = {ep.get("title", "").strip(): ep for ep in in_prog}
            for ep in episodes:
                match = prog_by_title.get(ep.get("title", "").strip())
                if match:
                    ep["playedUpTo"]    = match.get("playedUpTo", 0)
                    ep["playingStatus"] = match.get("playingStatus", 0)
        except Exception:
            pass

        return episodes

    # ── Queue endpoints ──

    def in_progress(self):
        return self._post("/user/in_progress").get("episodes", [])

    def new_releases(self):
        return self._post("/user/new_releases").get("episodes", [])

    def starred(self):
        return self._post("/user/starred").get("episodes", [])

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

    def sync_episode(self, podcast_uuid, episode_uuid, position_secs):
        """Push playback position to Pocket Casts."""
        try:
            self._post("/sync/update_episode_position", {
                "podcast":  podcast_uuid,
                "episode":  episode_uuid,
                "position": int(position_secs),
                "status":   2,
            })
        except Exception:
            pass

    def sync_file(self, file_uuid, position_secs):
        """Push file playback position to Pocket Casts."""
        try:
            self._post("/files", {"files": [{
                "uuid":          file_uuid,
                "playedUpTo":    int(position_secs),
                "playingStatus": 2,
            }]})
        except Exception:
            pass

    def delete_file(self, file_uuid):
        """Delete a file from Pocket Casts cloud storage."""
        r = self.client.delete(f"{BASE_URL}/files/{file_uuid}")
        r.raise_for_status()

    def mark_played(self, podcast_uuid, episode_uuid):
        try:
            self._post("/sync/update_episode", {
                "podcast": podcast_uuid,
                "episode": episode_uuid,
                "status":  3,
            })
        except Exception:
            pass


# ─────────────────────────────────────────────
# MPV IPC
# ─────────────────────────────────────────────

class MPV:
    def __init__(self):
        self.sock = None
        self._id  = 0
        self.proc = None

    def launch(self, url, speed=1.0, start_pos=0, skip_silence=0):
        try:
            os.unlink(SOCKET_PATH)
        except Exception:
            pass

        cmd = [
            "mpv", "--no-video",
            f"--input-ipc-server={SOCKET_PATH}",
            "--really-quiet",
            f"--speed={speed}",
        ]
        if start_pos and int(start_pos) > 5:
            cmd += [f"--start={int(start_pos)}"]

        af = SILENCE_FILTERS.get(skip_silence)
        if af:
            cmd += [f"--af={af}"]

        cmd.append(url)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for _ in range(20):
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(SOCKET_PATH)
                self.sock.settimeout(0.5)
                return True
            except Exception:
                self.sock = None
                time.sleep(0.2)
        return False

    def _cmd(self, cmd):
        if not self.sock:
            return None
        try:
            self._id += 1
            msg = json.dumps({"command": cmd, "request_id": self._id}) + "\n"
            self.sock.sendall(msg.encode())
            buf = b""
            while True:
                try:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    if b"\n" in buf:
                        break
                except socket.timeout:
                    break
            for line in buf.split(b"\n"):
                line = line.strip()
                if line:
                    try:
                        resp = json.loads(line)
                        if resp.get("request_id") == self._id:
                            return resp.get("data")
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    # Properties
    def get_position(self):   return self._cmd(["get_property", "time-pos"]) or 0.0
    def get_duration(self):   return self._cmd(["get_property", "duration"]) or 0.0
    def get_paused(self):     return self._cmd(["get_property", "pause"]) or False
    def get_speed(self):      return self._cmd(["get_property", "speed"]) or 1.0
    def is_done(self):        return self._cmd(["get_property", "idle-active"]) is True
    def get_chapter(self):    return self._cmd(["get_property", "chapter"]) or 0
    def get_chapter_list(self):
        data = self._cmd(["get_property", "chapter-list"])
        return data if isinstance(data, list) else []

    # Commands
    def next_chapter(self):   self._cmd(["add", "chapter",  1])
    def prev_chapter(self):   self._cmd(["add", "chapter", -1])
    def pause_toggle(self):   self._cmd(["cycle", "pause"])
    def seek(self, secs):     self._cmd(["seek", secs, "relative"])
    def set_speed(self, s):   self._cmd(["set_property", "speed", s])

    def quit(self):
        self._cmd(["quit"])
        if self.proc:
            try:
                self.proc.wait(timeout=2)
            except Exception:
                self.proc.kill()
        try:
            self.sock.close()
        except Exception:
            pass
        self.sock = None
        self.proc = None

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None


# ─────────────────────────────────────────────
# Login screen
# ─────────────────────────────────────────────

def curses_login(stdscr):
    curses.curs_set(1)
    curses.echo()
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    cx = (w - 30) // 2

    stdscr.addstr(h // 2 - 3, cx, "  pocketcli - Login  ", curses.A_REVERSE)
    stdscr.addstr(h // 2 - 1, cx, "Email: ")
    stdscr.refresh()
    email = stdscr.getstr(h // 2 - 1, cx + 7, 50).decode()

    stdscr.addstr(h // 2 + 1, cx, "Password: ")
    stdscr.refresh()
    curses.noecho()
    password = stdscr.getstr(h // 2 + 1, cx + 10, 50).decode()

    stdscr.addstr(h // 2 + 3, cx, "Authenticating...")
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
            return None, "Login failed"
        save_config(email, token, data.get("uuid", ""))
        return token, None
    except Exception as e:
        return None, str(e)


# ─────────────────────────────────────────────
# TUI
# ─────────────────────────────────────────────

class PocketTUI:

    # View identifiers
    VIEW_PODCASTS = "podcasts"
    VIEW_EPISODES = "episodes"
    VIEW_QUEUE    = "queue"      # in_progress | new | starred
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
        self.episodes   = []
        self.queue_items = []
        self.files_items = []
        self.queue_mode  = "in_progress"   # in_progress | new | starred
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
        self.playing_pod  = None
        self.playing_ep   = None
        self.speed_idx    = 2        # index into SPEEDS; default 1.0x
        self.skip_silence = 0        # 0=off 1=normal 2=medium 3=aggressive
        self.last_sync    = 0
        self.sleep_timer_end  = 0    # epoch when timer fires, 0=inactive
        self.show_sleep_menu  = False
        self.sleep_cursor     = 0

        # ── Overlays ──
        self.show_desc   = False
        self.desc_offset = 0
        self.show_keys   = False
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
        self.current_theme = 0

        curses.start_color()
        curses.use_default_colors()
        self._truecolor = curses.can_change_color() and curses.COLORS >= 256
        self._tc_ids    = list(range(16, 25))
        self._apply_theme(0)

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
            return _hex_to_ansi(hex_val) if hex_val else curses.COLOR_WHITE

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
                self.status("")
            except Exception as e:
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
                if not eps and feed_url:
                    # Retry without cached feed URL
                    eps = self.api.podcast_episodes(podcast["uuid"], podcast.get("title", ""))
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

    def load_queue(self):
        self.status("Loading...")
        def _load():
            try:
                if self.queue_mode == "in_progress":
                    items = self.api.in_progress()
                elif self.queue_mode == "new":
                    items = self.api.new_releases()
                else:
                    items = self.api.starred()
                self.queue_items = items
                self.q_cursor = self.q_offset = 0
                self.status("")
            except Exception as e:
                self.status(f"Error: {e}", error=True)
        threading.Thread(target=_load, daemon=True).start()

    def load_files(self):
        self.status("Loading files...")
        def _load():
            try:
                self.files_items = self.api.files()
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
        if self.mpv.is_running() and self.playing_pod and self.playing_ep:
            self._push_sync(self.mpv.get_position())
            self.mpv.quit()

    def _push_sync(self, pos):
        """Push position to API based on whether it's a file or episode."""
        pod = self.playing_pod
        ep  = self.playing_ep
        if not pod or not ep:
            return
        def _sync():
            if pod["uuid"] == "__files__":
                self.api.sync_file(ep["uuid"], pos)
            else:
                self.api.sync_episode(pod["uuid"], ep["uuid"], pos)
        threading.Thread(target=_sync, daemon=True).start()

    def play(self, podcast_dict, episode_dict):
        self._stop_current()
        self.playing_pod = podcast_dict
        self.playing_ep  = episode_dict
        self.status("Fetching stream...")
        self.draw()

        url = self.api.episode_stream_url(podcast_dict["uuid"], episode_dict["uuid"])
        if not url:
            url = episode_dict.get("url") or episode_dict.get("streamUrl")
        if not url:
            self.status("Could not get episode URL", error=True)
            return

        saved = int(episode_dict.get("playedUpTo") or episode_dict.get("played_up_to") or 0)
        ok    = self.mpv.launch(url, speed=SPEEDS[self.speed_idx],
                                start_pos=saved, skip_silence=self.skip_silence)
        if not ok:
            self.status("Could not start mpv", error=True)
            return

        self.last_sync = time.time()
        self.status(f"Playing: {episode_dict.get('title', '')[:50]}")

    def play_file(self, file_dict):
        self._stop_current()
        self.playing_pod = {"uuid": "__files__", "title": "Files"}
        self.playing_ep  = file_dict
        self.status("Fetching stream...")
        self.draw()

        try:
            url = self.api.file_stream_url(file_dict["uuid"])
        except Exception:
            url = None
        if not url:
            self.status("Could not get file URL", error=True)
            return

        saved = int(file_dict.get("playedUpTo") or 0)
        ok    = self.mpv.launch(url, speed=SPEEDS[self.speed_idx],
                                start_pos=saved, skip_silence=self.skip_silence)
        if not ok:
            self.status("Could not start mpv", error=True)
            return

        self.last_sync = time.time()
        self.status(f"Playing: {file_dict.get('title', '')[:50]}")

    def sync_position(self):
        """Periodic sync every 30s while playing."""
        if not self.mpv.is_running() or not self.playing_pod or not self.playing_ep:
            return
        now = time.time()
        if now - self.last_sync >= 30:
            self.last_sync = now
            self._push_sync(self.mpv.get_position())

    def check_sleep_timer(self):
        """Pause playback when sleep timer expires."""
        if not self.sleep_timer_end or not self.mpv.is_running():
            return
        if time.time() >= self.sleep_timer_end:
            self.sleep_timer_end = 0
            if self.mpv.is_running():
                self._push_sync(self.mpv.get_position())
                self.mpv.pause_toggle()
                self.status("Sleep timer — paused.")

    def check_finished(self):
        """Mark episode as played when mpv exits naturally."""
        if not self.mpv.is_running() and self.playing_ep and self.mpv.proc is not None:
            if self.playing_pod and self.playing_pod["uuid"] != "__files__":
                pod, ep = self.playing_pod, self.playing_ep
                threading.Thread(
                    target=lambda: self.api.mark_played(pod["uuid"], ep["uuid"]),
                    daemon=True,
                ).start()
            self.playing_ep  = None
            self.playing_pod = None
            self.mpv.proc    = None

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
                self.episodes  = self.api.podcast_episodes_from_rss(feed_url) if feed_url else []
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

        # Overlays (drawn last, on top)
        self._draw_desc_overlay()
        self._draw_search_overlay()
        self._draw_theme_overlay()
        self._draw_keymap_overlay()
        self._draw_sleep_menu_overlay()
        self._draw_unsub_confirm_overlay()
        self._draw_delete_file_overlay()

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
        x = 1
        for i, (key, label, _, _) in enumerate(TABS):
            is_active  = i == active_idx
            is_focused = (self.focus_level == self.FOCUS_TABBAR and i == self.tab_cursor)
            tag = f"[{key}] {label}"

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
        stat  = int(f.get("playingStatus", 0) or 0)

        is_second = self.del_file_step == 2
        played = stat == 3 or (dur and pos >= dur - 30)

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
                            lambda _, ep: (
                                trunc(ep.get("title", ""), w - 30),
                                f"{trunc(ep.get('podcastTitle', ''), 14)}  "
                                f"{fmt_dur(ep.get('playedUpTo', 0))}/{fmt_dur(ep.get('duration', 0))}",
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
            msg = "Loading..." if "Loading" in self.status_msg else "No results."
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

        # Chapter info (cached every 10 ticks to reduce IPC calls)
        chapter_name = ""
        if self.mpv.is_running():
            ch_idx = self.mpv.get_chapter()
            if not hasattr(self, "_ch_list_cache") or self._ch_list_tick % 10 == 0:
                self._ch_list_cache = self.mpv.get_chapter_list()
                self._ch_list_tick  = 0
            self._ch_list_tick = getattr(self, "_ch_list_tick", 0) + 1
            ch_list = self._ch_list_cache
            if ch_list and ch_idx is not None and 0 <= ch_idx < len(ch_list):
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
                self.scr.addstr(top + 1, 18, "  press space to continue")
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
            ("Spc", "pause"), ("←→", "±30s"), ("n/N", "chapter"),
            ("]", "faster"), ("[", "slower"), ("S", "silence"),
            ("z", "sleep"),  ("t", "theme"),  ("?", "keys"), ("q", "quit"),
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

        NAV_BADGES = {
            self.VIEW_PODCASTS: [("↑↓", "navigate"), ("Enter", "open"), ("u", "unsub"),  ("/", "search"), ("t", "theme"), ("?", "keys"), ("q", "quit")],
            self.VIEW_EPISODES: [("↑↓", "navigate"), ("Enter", "play"), ("d", "desc"),   ("/", "search"), ("Esc", "back"), ("?", "keys"), ("q", "quit")],
            self.VIEW_QUEUE:    [("↑↓", "navigate"), ("Enter", "play"), ("d", "desc"),   ("?", "keys"), ("q", "quit")],
            self.VIEW_FILES:    [("↑↓", "navigate"), ("Enter", "play"), ("x", "delete"), ("?", "keys"), ("q", "quit")],
            self.VIEW_DISCOVER: [("↑↓", "navigate"), ("Enter", "subscribe"), ("/", "search"), ("?", "keys"), ("q", "quit")],
        }
        self._draw_badges(y, w, NAV_BADGES.get(self.view, []))

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
        oh = len(self.THEMES) + 4
        ox = (w - ow) // 2
        oy = max(1, (h - oh) // 2)

        self._overlay_box(oy, ox, oh, ow, title="Theme")

        for i, theme in enumerate(self.THEMES):
            sel    = i == self.theme_cursor
            active = i == self.current_theme
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
        ow = min(w - 6, 60)
        oh = 34
        ox = (w - ow) // 2
        oy = max(1, (h - oh) // 2)

        self._overlay_box(oy, ox, oh, ow, title="Keymap")

        KEYS = [
            ("Navigation",       None),
            ("Tab",              "Focus: content → tab bar → sub-menu"),
            ("Shift+Tab",        "Focus: reverse direction"),
            ("← →",             "Move between tabs or sub-menu items"),
            ("Enter",            "Select focused tab / item"),
            ("1-6",              "Jump directly to tab"),
            ("↑↓ / j k",        "Navigate list"),
            ("PgUp PgDn",        "Jump page"),
            ("Esc",              "Back / close overlay / lose focus"),
            ("/",                "Search"),
            ("d",                "Episode description"),
            ("u",                "Unsubscribe (Podcasts tab)"),
            ("x",                "Delete file from cloud (Files tab)"),
            ("",                 None),
            ("Player",           None),
            ("Space / p",        "Play / Pause"),
            ("← →",             "Seek ±30s"),
            ("n / N",            "Next / Prev chapter"),
            ("] / [",            "Speed up / down"),
            ("S",                "Cycle skip silence"),
            ("z",                "Sleep timer — 5/15/30/60 min (↑↓ Enter to select)"),
            ("",                 None),
            ("Other",            None),
            ("t",                "Theme selector"),
            ("?",                "This keymap"),
            ("q",                "Quit"),
        ]

        row = 1
        for key, action in KEYS:
            if row >= oh - 1:
                break
            try:
                if action is None and key == "":
                    row += 1
                    continue
                elif action is None:
                    self.scr.attron(curses.color_pair(2) | curses.A_BOLD)
                    self.scr.addstr(oy + row, ox + 2, key)
                    self.scr.attroff(curses.color_pair(2) | curses.A_BOLD)
                else:
                    self.scr.attron(curses.color_pair(3))
                    self.scr.addstr(oy + row, ox + 4, f"{key:<16}")
                    self.scr.attroff(curses.color_pair(3))
                    self.scr.addstr(oy + row, ox + 21, action)
            except Exception:
                pass
            row += 1

        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(oy + oh - 1, ox + 2, "┤ ? / Esc = close ├")
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

    def handle_key(self, key):
        vis = self._visible_rows()

        # ── q: close overlays then quit ──
        if key in (ord("q"), ord("Q")):
            if self.show_desc:          self.show_desc = False
            elif self.searching:
                self.searching = False; self.search_query = ""
            elif self.discover_searching:
                self._close_discover_search()
            elif self.unsub_confirm:
                self.unsub_confirm = False; self.unsub_target = None
            elif self.show_sleep_menu:
                self.show_sleep_menu = False
            elif self.del_file_step > 0:
                self.del_file_step = 0; self.del_file_target = None
            elif self.focus_level != self.FOCUS_CONTENT:
                self.focus_level = self.FOCUS_CONTENT
            else:
                return False
            return True

        # ── Esc: back in priority order ──
        if key == 27:
            if self.show_keys:      self.show_keys  = False
            elif self.show_desc:    self.show_desc  = False
            elif self.show_themes:  self.show_themes = False
            elif self.unsub_confirm:
                self.unsub_confirm = False; self.unsub_target = None
            elif self.show_sleep_menu:
                self.show_sleep_menu = False
            elif self.del_file_step > 0:
                self.del_file_step = 0; self.del_file_target = None
            elif self.searching:
                self.searching = False; self.search_query = ""
            elif self.discover_searching:
                self._close_discover_search()
            elif self.focus_level == self.FOCUS_SUBMENU:
                self.focus_level = self.FOCUS_CONTENT
            elif self.focus_level == self.FOCUS_TABBAR:
                self.focus_level = self.FOCUS_CONTENT
            elif self.view == self.VIEW_EPISODES:
                self.view = self.VIEW_PODCASTS
            return True

        # ── Capture modes ──
        if self.searching:
            return self._handle_search_key(key)
        if self.discover_searching:
            self._handle_discover_key(key)
            return True

        # ── Overlay captures ──
        if self.show_sleep_menu:
            options = self._sleep_options()
            if key in (curses.KEY_DOWN, ord("j")):
                self.sleep_cursor = (self.sleep_cursor + 1) % len(options)
            elif key in (curses.KEY_UP, ord("k")):
                self.sleep_cursor = (self.sleep_cursor - 1) % len(options)
            elif key in (curses.KEY_ENTER, 10, 13):
                _, mins = options[self.sleep_cursor]
                if mins == -1:
                    self.sleep_timer_end = 0
                    self.status("Sleep timer cancelled.")
                elif mins == 0:
                    pass  # not used anymore
                else:
                    self.sleep_timer_end = time.time() + mins * 60
                    self.status(f"Sleep timer set: {mins} min")
                self.show_sleep_menu = False
            elif key in (27, ord("z")):
                self.show_sleep_menu = False
            return True

        if self.show_themes:
            if key in (curses.KEY_DOWN, ord("j")):
                self.theme_cursor = (self.theme_cursor + 1) % len(self.THEMES)
            elif key in (curses.KEY_UP, ord("k")):
                self.theme_cursor = (self.theme_cursor - 1) % len(self.THEMES)
            elif key in (curses.KEY_ENTER, 10, 13):
                self.current_theme = self.theme_cursor
                self._apply_theme(self.current_theme)
                self.show_themes   = False
                self.status(f"Theme: {self.THEMES[self.current_theme]['name']}")
            return True

        if self.show_desc:
            if key in (curses.KEY_DOWN, ord("j")):   self.desc_offset += 1
            elif key in (curses.KEY_UP, ord("k")):   self.desc_offset = max(0, self.desc_offset - 1)
            elif key in (ord("d"), ord("q")):         self.show_desc = False
            return True

        if self.unsub_confirm:
            if key in (ord("y"), ord("Y")):  self._do_unsubscribe()
            else:
                self.unsub_confirm = False; self.unsub_target = None
            return True

        if self.del_file_step > 0:
            if key in (ord("y"), ord("Y")):
                if self.del_file_step == 1:
                    f    = self.del_file_target
                    dur  = int(f.get("duration", 0) or 0)
                    pos  = int(f.get("playedUpTo", 0) or 0)
                    stat = int(f.get("playingStatus", 0) or 0)
                    if stat == 3 or (dur and pos >= dur - 30):
                        self._do_delete_file()
                    else:
                        self.del_file_step = 2
                else:
                    self._do_delete_file()
            else:
                self.del_file_step = 0; self.del_file_target = None
            return True

        # ── Tab / Shift+Tab: cycle focus ──
        KEY_TAB       = 9
        KEY_SHIFT_TAB = 353

        if key == KEY_TAB:
            self._focus_next()
            return True
        if key == KEY_SHIFT_TAB:
            self._focus_prev()
            return True

        # ── Focus-aware navigation ──
        if self.focus_level == self.FOCUS_TABBAR:
            if key in (curses.KEY_RIGHT, ord("l")):
                self.tab_cursor = (self.tab_cursor + 1) % len(TABS)
            elif key in (curses.KEY_LEFT, ord("h")):
                self.tab_cursor = (self.tab_cursor - 1) % len(TABS)
            elif key in (curses.KEY_ENTER, 10, 13):
                self._activate_tab(self.tab_cursor)
            return True

        if self.focus_level == self.FOCUS_SUBMENU and self.view == self.VIEW_DISCOVER:
            if key in (curses.KEY_RIGHT, ord("l")):
                self.discover_mode_cursor = (self.discover_mode_cursor + 1) % len(DISCOVER_MODES)
            elif key in (curses.KEY_LEFT, ord("h")):
                self.discover_mode_cursor = (self.discover_mode_cursor - 1) % len(DISCOVER_MODES)
            elif key in (curses.KEY_ENTER, 10, 13):
                mode = DISCOVER_MODES[self.discover_mode_cursor][0]
                self.discover_query = ""
                self.load_discover_list(mode)
                self.focus_level = self.FOCUS_CONTENT
            return True

        # ── Global toggles ──
        if key == ord("?"):
            self.show_keys = not self.show_keys
            return True
        if key == ord("t"):
            self.show_themes  = not self.show_themes
            self.theme_cursor = self.current_theme
            return True

        # ── Number keys: jump to tab ──
        for i, (k, _, _, _) in enumerate(TABS):
            if key == ord(k):
                self._activate_tab(i)
                return True

        # ── Search ──
        if key == ord("/") and self.view in (self.VIEW_EPISODES, self.VIEW_PODCASTS):
            self.searching          = True
            self.search_query       = ""
            self.search_results     = []
            self.pod_search_results = []
            self.search_cursor      = self.search_offset     = 0
            self.pod_search_cursor  = self.pod_search_offset = 0
            return True

        if key == ord("/") and self.view == self.VIEW_DISCOVER:
            self.discover_searching = True
            return True

        # ── Unsubscribe ──
        if key == ord("u") and self.view == self.VIEW_PODCASTS and self.podcasts:
            self.unsub_target  = self.podcasts[self.pod_cursor]
            self.unsub_confirm = True
            return True

        # ── Player controls ──
        if key in (ord("p"), ord(" ")):
            if self.mpv.is_running():
                self.mpv.pause_toggle()
                if self.playing_pod and self.playing_ep:
                    self._push_sync(self.mpv.get_position())
                    self.last_sync = time.time()
            elif self.playing_ep:
                if self.playing_pod and self.playing_pod.get("uuid") == "__files__":
                    self.play_file(self.playing_ep)
                else:
                    self.play(self.playing_pod or {"uuid": "", "title": ""}, self.playing_ep)
            return True

        if key == curses.KEY_RIGHT and self.mpv.is_running():
            self.mpv.seek(30); return True
        if key == curses.KEY_LEFT and self.mpv.is_running():
            self.mpv.seek(-30); return True
        if key == ord("n") and self.mpv.is_running():
            self.mpv.next_chapter(); return True
        if key == ord("N") and self.mpv.is_running():
            self.mpv.prev_chapter(); return True
        if key == ord("]") and self.mpv.is_running():
            self.speed_idx = min(len(SPEEDS) - 1, self.speed_idx + 1)
            self.mpv.set_speed(SPEEDS[self.speed_idx])
            self.status(f"Speed: {SPEEDS[self.speed_idx]}x")
            return True
        if key == ord("[") and self.mpv.is_running():
            self.speed_idx = max(0, self.speed_idx - 1)
            self.mpv.set_speed(SPEEDS[self.speed_idx])
            self.status(f"Speed: {SPEEDS[self.speed_idx]}x")
            return True
        if key == ord("z"):
            self.show_sleep_menu = not self.show_sleep_menu
            if self.show_sleep_menu:
                self.sleep_cursor = 0
            return True

        if key == ord("S") and self.playing_ep:
            self.skip_silence = (self.skip_silence + 1) % 4
            labels = ["off", "normal", "medium", "aggressive"]
            self.status(f"Skip silence: {labels[self.skip_silence]} (applies on next play)")
            return True

        # ── View-specific navigation ──
        if self.view == self.VIEW_PODCASTS:
            if key in (curses.KEY_DOWN, ord("j")):
                self.pod_cursor, self.pod_offset = self._scroll(self.pod_cursor, self.pod_offset,  1, len(self.podcasts), vis)
            elif key in (curses.KEY_UP, ord("k")):
                self.pod_cursor, self.pod_offset = self._scroll(self.pod_cursor, self.pod_offset, -1, len(self.podcasts), vis)
            elif key == curses.KEY_NPAGE:
                self.pod_cursor, self.pod_offset = self._scroll(self.pod_cursor, self.pod_offset,  vis, len(self.podcasts), vis)
            elif key == curses.KEY_PPAGE:
                self.pod_cursor, self.pod_offset = self._scroll(self.pod_cursor, self.pod_offset, -vis, len(self.podcasts), vis)
            elif key in (curses.KEY_ENTER, 10, 13) and self.podcasts:
                self.load_episodes(self.podcasts[self.pod_cursor])

        elif self.view == self.VIEW_EPISODES:
            if key in (curses.KEY_DOWN, ord("j")):
                self.ep_cursor, self.ep_offset = self._scroll(self.ep_cursor, self.ep_offset,  1, len(self.episodes), vis)
            elif key in (curses.KEY_UP, ord("k")):
                self.ep_cursor, self.ep_offset = self._scroll(self.ep_cursor, self.ep_offset, -1, len(self.episodes), vis)
            elif key == curses.KEY_NPAGE:
                self.ep_cursor, self.ep_offset = self._scroll(self.ep_cursor, self.ep_offset,  vis, len(self.episodes), vis)
            elif key == curses.KEY_PPAGE:
                self.ep_cursor, self.ep_offset = self._scroll(self.ep_cursor, self.ep_offset, -vis, len(self.episodes), vis)
            elif key in (curses.KEY_ENTER, 10, 13) and self.episodes:
                self.play(self.current_pod, self.episodes[self.ep_cursor])
            elif key in (curses.KEY_BACKSPACE, 127, ord("b")):
                self.view = self.VIEW_PODCASTS
            elif key == ord("d"):
                self.show_desc = True; self.desc_offset = 0

        elif self.view == self.VIEW_QUEUE:
            if key in (curses.KEY_DOWN, ord("j")):
                self.q_cursor, self.q_offset = self._scroll(self.q_cursor, self.q_offset,  1, len(self.queue_items), vis)
            elif key in (curses.KEY_UP, ord("k")):
                self.q_cursor, self.q_offset = self._scroll(self.q_cursor, self.q_offset, -1, len(self.queue_items), vis)
            elif key == curses.KEY_NPAGE:
                self.q_cursor, self.q_offset = self._scroll(self.q_cursor, self.q_offset,  vis, len(self.queue_items), vis)
            elif key == curses.KEY_PPAGE:
                self.q_cursor, self.q_offset = self._scroll(self.q_cursor, self.q_offset, -vis, len(self.queue_items), vis)
            elif key in (curses.KEY_ENTER, 10, 13) and self.queue_items:
                ep       = self.queue_items[self.q_cursor]
                pod_uuid = ep.get("podcastUuid") or ep.get("podcast_uuid") or ep.get("podcast")
                self.play({"uuid": pod_uuid, "title": ep.get("podcastTitle", "")}, ep)
            elif key == ord("d"):
                self.show_desc = True; self.desc_offset = 0

        elif self.view == self.VIEW_FILES:
            if key in (curses.KEY_DOWN, ord("j")):
                self.f_cursor, self.f_offset = self._scroll(self.f_cursor, self.f_offset,  1, len(self.files_items), vis)
            elif key in (curses.KEY_UP, ord("k")):
                self.f_cursor, self.f_offset = self._scroll(self.f_cursor, self.f_offset, -1, len(self.files_items), vis)
            elif key == curses.KEY_NPAGE:
                self.f_cursor, self.f_offset = self._scroll(self.f_cursor, self.f_offset,  vis, len(self.files_items), vis)
            elif key == curses.KEY_PPAGE:
                self.f_cursor, self.f_offset = self._scroll(self.f_cursor, self.f_offset, -vis, len(self.files_items), vis)
            elif key in (curses.KEY_ENTER, 10, 13) and self.files_items:
                self.play_file(self.files_items[self.f_cursor])
            elif key == ord("x") and self.files_items:
                self.del_file_target = self.files_items[self.f_cursor]
                self.del_file_step   = 1

        elif self.view == self.VIEW_DISCOVER:
            list_vis = self._visible_rows() - 2
            if key in (curses.KEY_DOWN, ord("j")):
                self.discover_cursor, self.discover_offset = self._scroll(
                    self.discover_cursor, self.discover_offset, 1, len(self.discover_results), list_vis)
            elif key in (curses.KEY_UP, ord("k")):
                self.discover_cursor, self.discover_offset = self._scroll(
                    self.discover_cursor, self.discover_offset, -1, len(self.discover_results), list_vis)
            elif key == curses.KEY_NPAGE:
                self.discover_cursor, self.discover_offset = self._scroll(
                    self.discover_cursor, self.discover_offset, list_vis, len(self.discover_results), list_vis)
            elif key == curses.KEY_PPAGE:
                self.discover_cursor, self.discover_offset = self._scroll(
                    self.discover_cursor, self.discover_offset, -list_vis, len(self.discover_results), list_vis)
            elif key in (curses.KEY_ENTER, 10, 13) and self.discover_results:
                self._do_subscribe(self.discover_results[self.discover_cursor])

        return True

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
        elif key == 27:
            self.discover_searching = False
            if not self.discover_query:
                m = self.discover_list_mode
                self.discover_results = self.discover_lists.get(m, [])
        elif key in (curses.KEY_ENTER, 10, 13):
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
        """On startup, set playing_ep to the most recently played item."""
        try:
            in_prog  = self.api.in_progress()
            last_ep  = in_prog[0] if in_prog else None

            files    = self.api.files()
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
                        from datetime import datetime
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

            if not recent:
                return

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

    # ─────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────

    def run(self):
        self.load_podcasts()
        self._load_last_played()

        while True:
            self.draw()
            self.sync_position()
            self.check_finished()
            self.check_sleep_timer()

            self.scr.timeout(100)
            key = self.scr.getch()
            if key != -1 and not self.handle_key(key):
                break

        # Final sync on exit
        if self.mpv.is_running():
            self._push_sync(self.mpv.get_position())
            self.mpv.quit()


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main(stdscr):
    token = load_token()
    if not token:
        token, err = curses_login(stdscr)
        if not token:
            curses.endwin()
            print(f"Login error: {err}")
            sys.exit(1)
    api = API(token)
    PocketTUI(stdscr, api).run()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
