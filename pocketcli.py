#!/usr/bin/env python3
"""
pocketcli - Terminal UI for Pocket Casts
Navega podcasts, episodios y reproduce con sync bidireccional
"""

VERSION = "1.18.0"
BUILD   = "2026-06-04"

import os
import sys
import json
import time
import socket
import curses
import subprocess
import configparser
import threading
from pathlib import Path

import httpx

# ─────────────────────────────────────────────
# Config / Auth
# ─────────────────────────────────────────────

CONFIG_DIR  = Path.home() / ".config" / "pocketcli"
CONFIG_FILE = CONFIG_DIR / "config.ini"
SOCKET_PATH = "/tmp/pocketcli-mpv.sock"
BASE_URL    = "https://api.pocketcasts.com"


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
# API
# ─────────────────────────────────────────────

class API:
    def __init__(self, token):
        self.token = token
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )

    def _post(self, path, data=None):
        r = self.client.post(f"{BASE_URL}{path}", json=data or {})
        r.raise_for_status()
        return r.json()

    def _get(self, path):
        r = self.client.get(f"{BASE_URL}{path}")
        r.raise_for_status()
        return r.json()

    def subscribed_podcasts(self):
        return self._post("/user/podcast/list", {"v": 1}).get("podcasts", [])

    def podcast_feed_url(self, podcast_title):
        """Busca el RSS feed via iTunes API"""
        try:
            import urllib.parse
            term = urllib.parse.quote(podcast_title)
            # Cliente limpio sin Authorization header
            r = httpx.get(
                f"https://itunes.apple.com/search?term={term}&entity=podcast&limit=5",
                timeout=10,
            )
            results = r.json().get("results", [])
            if results:
                return results[0].get("feedUrl")
        except Exception:
            pass
        return None

    def podcast_episodes_from_rss(self, feed_url, sync_data=None):
        """Parsea el RSS y cruza con datos de sync de Pocket Casts"""
        import xml.etree.ElementTree as ET
        import urllib.request

        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "pocketcli/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
            channel = root.find("channel")
            if channel is None:
                return []

            # sync_data: dict uuid -> {playedUpTo, playingStatus}
            sync = sync_data or {}

            episodes = []
            for item in channel.findall("item"):
                title = item.findtext("title", "").strip()
                guid  = item.findtext("guid", "").strip()
                pub   = item.findtext("pubDate", "")
                url_el = item.find("enclosure")
                url   = url_el.get("url", "") if url_el is not None else ""

                # Duration from itunes:duration
                dur_str = item.findtext("itunes:duration", "", ns).strip()
                duration = 0
                if dur_str:
                    parts = dur_str.split(":")
                    try:
                        if len(parts) == 3:
                            duration = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                        elif len(parts) == 2:
                            duration = int(parts[0])*60 + int(parts[1])
                        else:
                            duration = int(parts[0])
                    except Exception:
                        pass

                # Date
                pub_iso = ""
                if pub:
                    try:
                        from email.utils import parsedate_to_datetime
                        pub_iso = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
                    except Exception:
                        pub_iso = pub[:10]

                # Description - strip HTML tags
                desc_raw = (
                    item.findtext("itunes:summary", "", ns) or
                    item.findtext("description", "") or ""
                ).strip()
                import re
                desc = re.sub(r"<[^>]+>", "", desc_raw).strip()

                ep = {
                    "title": title,
                    "uuid": guid,
                    "url": url,
                    "duration": duration,
                    "publishedAt": pub_iso,
                    "description": desc,
                    "playedUpTo": 0,
                    "playingStatus": 0,
                }
                # Cruzar con sync si el guid coincide con algun uuid conocido
                if guid in sync:
                    ep["playedUpTo"] = sync[guid].get("playedUpTo", 0)
                    ep["playingStatus"] = sync[guid].get("playingStatus", 0)

                episodes.append(ep)

            return episodes
        except Exception:
            return []

    def podcast_episodes(self, podcast_uuid, podcast_title=""):
        """Fetch episodes from RSS feed, crossing with in_progress by title"""
        feed_url = self.podcast_feed_url(podcast_title)
        if not feed_url:
            return self._post("/user/podcast/episodes", {
                "uuid": podcast_uuid, "page": 0, "sort": 3,
            }).get("episodes", [])

        episodes = self.podcast_episodes_from_rss(feed_url)

        # Cross with in_progress by title to get playedUpTo
        try:
            in_prog = self._post("/user/in_progress").get("episodes", [])
            prog_by_title = {ep.get("title", "").strip(): ep for ep in in_prog}
            for ep in episodes:
                match = prog_by_title.get(ep.get("title", "").strip())
                if match:
                    ep["playedUpTo"]    = match.get("playedUpTo", 0)
                    ep["playingStatus"] = match.get("playingStatus", 0)
        except Exception:
            pass

        return episodes

    def in_progress(self):
        return self._post("/user/in_progress").get("episodes", [])

    def new_releases(self):
        return self._post("/user/new_releases").get("episodes", [])

    def starred(self):
        return self._post("/user/starred").get("episodes", [])

    def files(self):
        return self._get("/files?include_bookmarks=true").get("files", [])

    def file_stream_url(self, file_uuid):
        return self._get(f"/files/play/{file_uuid}").get("url")

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
        # fallback: construir URL directa
        ep = self.client.get(
            f"{BASE_URL}/podcasts/episode",
            params={"podcast": podcast_uuid, "episode": episode_uuid},
        )
        if ep.status_code == 200:
            return ep.json().get("url") or ep.json().get("streamUrl")
        return None

    def update_position(self, podcast_uuid, episode_uuid, position_secs):
        try:
            self._post("/sync/update_episode_position", {
                "podcast": podcast_uuid,
                "episode": episode_uuid,
                "position": int(position_secs),
                "status": 2,
            })
        except Exception:
            pass

    def mark_played(self, podcast_uuid, episode_uuid):
        try:
            self._post("/sync/update_episode", {
                "podcast": podcast_uuid,
                "episode": episode_uuid,
                "status": 3,
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
        cmd = ["mpv", "--no-video", f"--input-ipc-server={SOCKET_PATH}",
               "--really-quiet", f"--speed={speed}"]
        if start_pos and int(start_pos) > 5:
            cmd += [f"--start={int(start_pos)}"]
        if skip_silence == 1:
            cmd += ["--af=lavfi=[silenceremove=start_periods=1:start_silence=0.5:start_threshold=-40dB:stop_periods=1:stop_silence=0.5:stop_threshold=-40dB]"]
        elif skip_silence == 2:
            cmd += ["--af=lavfi=[silenceremove=start_periods=1:start_silence=0.3:start_threshold=-35dB:stop_periods=1:stop_silence=0.3:stop_threshold=-35dB]"]
        elif skip_silence == 3:
            cmd += ["--af=lavfi=[silenceremove=start_periods=1:start_silence=0.15:start_threshold=-30dB:stop_periods=1:stop_silence=0.15:stop_threshold=-30dB]"]
        cmd.append(url)
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # connect socket
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

    def get_position(self):  return self._cmd(["get_property", "time-pos"]) or 0.0
    def get_duration(self):  return self._cmd(["get_property", "duration"]) or 0.0
    def get_paused(self):    return self._cmd(["get_property", "pause"]) or False
    def get_speed(self):     return self._cmd(["get_property", "speed"]) or 1.0
    def is_done(self):       return self._cmd(["get_property", "idle-active"]) is True

    def pause_toggle(self):  self._cmd(["cycle", "pause"])
    def seek(self, secs):    self._cmd(["seek", secs, "relative"])
    def set_speed(self, s):  self._cmd(["set_property", "speed", s])
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
# Helpers
# ─────────────────────────────────────────────

def fmt_dur(secs):
    if not secs:
        return "--:--"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_date(iso):
    if not iso:
        return ""
    try:
        return iso[:10]
    except Exception:
        return ""


def trunc(text, n):
    if not text:
        return ""
    return text if len(text) <= n else text[:n - 1] + "…"


SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]


# ─────────────────────────────────────────────
# Login screen (curses)
# ─────────────────────────────────────────────

def curses_login(stdscr):
    curses.curs_set(1)
    curses.echo()
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    stdscr.addstr(h // 2 - 3, (w - 30) // 2, "  pocketcli - Login  ", curses.A_REVERSE)
    stdscr.addstr(h // 2 - 1, (w - 30) // 2, "Email: ")
    stdscr.refresh()

    email = stdscr.getstr(h // 2 - 1, (w - 30) // 2 + 7, 50).decode()

    stdscr.addstr(h // 2 + 1, (w - 30) // 2, "Password: ")
    stdscr.refresh()
    curses.noecho()
    password = stdscr.getstr(h // 2 + 1, (w - 30) // 2 + 10, 50).decode()

    stdscr.addstr(h // 2 + 3, (w - 30) // 2, "Authenticating...")
    stdscr.refresh()

    try:
        r = httpx.post(
            f"{BASE_URL}/user/login",
            json={"email": email, "password": password, "scope": "webplayer"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        token = data.get("token")
        if not token:
            return None, "Login fallido"
        save_config(email, token, data.get("uuid", ""))
        return token, None
    except Exception as e:
        return None, str(e)


# ─────────────────────────────────────────────
# TUI App
# ─────────────────────────────────────────────

class PocketTUI:
    # Views
    VIEW_PODCASTS  = "podcasts"
    VIEW_EPISODES  = "episodes"
    VIEW_QUEUE     = "queue"     # in_progress / new / starred
    VIEW_FILES     = "files"
    VIEW_PLAYER    = "player"

    SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]

    def __init__(self, stdscr, api):
        self.scr = stdscr
        self.api = api
        self.mpv = MPV()

        # Navigation state
        self.view          = self.VIEW_PODCASTS
        self.podcasts      = []
        self.episodes      = []
        self.queue_items   = []
        self.files_items   = []
        self.queue_mode    = "in_progress"  # in_progress | new | starred
        self.pod_cursor    = 0
        self.ep_cursor     = 0
        self.q_cursor      = 0
        self.f_cursor      = 0
        self.pod_offset    = 0
        self.ep_offset     = 0
        self.q_offset      = 0
        self.f_offset      = 0
        self.current_pod   = None  # active podcast dict

        # Player state
        self.playing_ep     = None  # current episode dict
        self.playing_pod    = None  # current podcast dict
        self.speed_idx      = 2     # 1.0x por default
        self.skip_silence   = 0     # 0=off 1=normal 2=medium 3=aggressive
        self.last_sync      = 0
        self.status_msg     = ""
        self.status_timer   = 0
        self.show_desc      = False  # overlay de descripcion

        # Colors
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN,    -1)  # title
        curses.init_pair(2, curses.COLOR_GREEN,   -1)  # activo / play
        curses.init_pair(3, curses.COLOR_YELLOW,  -1)  # info / pos
        curses.init_pair(4, curses.COLOR_WHITE,   -1)  # normal
        curses.init_pair(5, curses.COLOR_BLACK,   curses.COLOR_CYAN)   # seleccion
        curses.init_pair(6, curses.COLOR_BLACK,   curses.COLOR_GREEN)  # player bar
        curses.init_pair(7, curses.COLOR_RED,     -1)  # error
        curses.init_pair(8, curses.COLOR_MAGENTA, -1)  # subtitle

        curses.curs_set(0)
        self.scr.nodelay(True)
        self.scr.keypad(True)

    # ── Data loading ──────────────────────────

    def load_podcasts(self):
        self.status("Loading podcasts...")
        try:
            self.podcasts = self.api.subscribed_podcasts()
            self.podcasts.sort(key=lambda p: p.get("title", "").lower())
            self.status("")
        except Exception as e:
            self.status(f"Error: {e}", error=True)

    def load_episodes(self, podcast):
        self.current_pod = podcast
        self.status(f"Loading {podcast.get('title', '')}...")
        try:
            self.episodes = self.api.podcast_episodes(
                podcast["uuid"], podcast.get("title", "")
            )
            self.ep_cursor = 0
            self.ep_offset = 0
            self.status(f"Loaded {len(self.episodes)} episodes")
        except Exception as e:
            self.status(f"Error loading episodes: {e}", error=True)

    def load_queue(self):
        self.status("Loading...")
        try:
            if self.queue_mode == "in_progress":
                self.queue_items = self.api.in_progress()
            elif self.queue_mode == "new":
                self.queue_items = self.api.new_releases()
            else:
                self.queue_items = self.api.starred()
            self.q_cursor = 0
            self.q_offset = 0
            self.status("")
        except Exception as e:
            self.status(f"Error: {e}", error=True)

    def load_files(self):
        self.status("Loading files...")
        try:
            self.files_items = self.api.files()
            self.f_cursor = 0
            self.f_offset = 0
            self.status("")
        except Exception as e:
            self.status(f"Error: {e}", error=True)

    # ── Player ────────────────────────────────

    def play_file(self, file_dict):
        if self.mpv.is_running():
            pos = self.mpv.get_position()
            if self.playing_pod and self.playing_ep:
                self.api.update_position(
                    self.playing_pod["uuid"], self.playing_ep["uuid"], pos
                )
            self.mpv.quit()

        # Wrap file as episode with special podcast_uuid
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
        speed = self.SPEEDS[self.speed_idx]
        ok = self.mpv.launch(url, speed=speed, start_pos=saved, skip_silence=self.skip_silence)
        if not ok:
            self.status("Could not start mpv", error=True)
            return

        self.last_sync = time.time()
        self.status(f"Playing: {file_dict.get('title', '')[:50]}")

    def play(self, podcast_dict, episode_dict):
        # Detener lo que haya
        if self.mpv.is_running():
            pos = self.mpv.get_position()
            if self.playing_pod and self.playing_ep:
                self.api.update_position(
                    self.playing_pod["uuid"], self.playing_ep["uuid"], pos
                )
            self.mpv.quit()

        self.playing_pod = podcast_dict
        self.playing_ep  = episode_dict
        self.status("Fetching stream...")
        self.draw()

        url = self.api.episode_stream_url(podcast_dict["uuid"], episode_dict["uuid"])
        if not url:
            # intentar campo directo
            url = episode_dict.get("url") or episode_dict.get("streamUrl")
        if not url:
            self.status("Could not get episode URL", error=True)
            return

        saved = int(episode_dict.get("playedUpTo") or episode_dict.get("played_up_to") or 0)
        speed = self.SPEEDS[self.speed_idx]
        ok = self.mpv.launch(url, speed=speed, start_pos=saved, skip_silence=self.skip_silence)
        if not ok:
            self.status("Could not start mpv", error=True)
            return

        self.last_sync = time.time()
        self.status(f"Playing: {episode_dict.get('title', '')[:50]}")

    def sync_position(self):
        if not self.mpv.is_running():
            return
        if not self.playing_pod or not self.playing_ep:
            return
        now = time.time()
        if now - self.last_sync >= 30:
            pos = self.mpv.get_position()
            if self.playing_pod["uuid"] == "__files__":
                # sync for files via different endpoint
                try:
                    self.api._post(f"/files/{self.playing_ep['uuid']}", {
                        "playedUpTo": int(pos),
                        "playingStatus": 2,
                    })
                except Exception:
                    pass
            else:
                self.api.update_position(
                    self.playing_pod["uuid"], self.playing_ep["uuid"], pos
                )
            self.last_sync = now

    def check_finished(self):
        # Only clear if mpv was running and finished, no si nunca arranco
        if not self.mpv.is_running() and self.playing_ep and self.mpv.proc is not None:
            if self.playing_pod and self.playing_ep:
                if self.playing_pod["uuid"] != "__files__":
                    self.api.mark_played(self.playing_pod["uuid"], self.playing_ep["uuid"])
            self.playing_ep  = None
            self.playing_pod = None
            self.mpv.proc    = None

    # ── Status bar ────────────────────────────

    def status(self, msg, error=False):
        self.status_msg   = msg
        self.status_error = error
        self.status_timer = time.time()

    # ── Drawing ───────────────────────────────

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()

        # Layout:
        # 0     : header bar (titulo + breadcrumb)
        # 1     : tabs
        # 2     : separator
        # 3..h-7: content list
        # h-6   : separator
        # h-5..h-2: player (4 lineas, solo si hay algo)
        # h-1   : status / controles

        self._draw_header(w)
        self._draw_tabs(w)
        self._draw_separator(2, w)

        player_h = 5 if (self.mpv.is_running() or self.playing_ep) else 0
        content_top = 3
        content_h   = h - content_top - player_h - 1

        import os
        with open("/tmp/pocketcli_draw.txt", "w") as f:
            f.write(f"h={h} w={w} player_h={player_h} playing_ep={bool(self.playing_ep)} mpv={self.mpv.is_running()}\n")

        self._draw_content(content_top, content_h, w)

        if player_h:
            self._draw_separator(h - player_h - 1, w, label=self._now_playing_label())
            self._draw_player(h - player_h, w)

        self._draw_footer(h - 1, w)
        self._draw_desc_overlay()
        self.scr.refresh()

    def _now_playing_label(self):
        if not self.playing_ep:
            return ""
        state = "⏸ PAUSED" if (self.mpv.is_running() and self.mpv.get_paused()) else "▶ NOW PLAYING"
        return f" {state} "

    def _draw_header(self, w):
        self.scr.attron(curses.color_pair(6) | curses.A_BOLD)
        self.scr.addstr(0, 0, " " * w)
        logo = f" P O C K E T C L I  v{VERSION}"
        self.scr.addstr(0, 0, logo)
        self.scr.attroff(curses.color_pair(6) | curses.A_BOLD)

        # Breadcrumb derecha
        if self.view == self.VIEW_EPISODES and self.current_pod:
            bc = trunc(self.current_pod.get("title", ""), 30)
            self.scr.attron(curses.color_pair(6))
            self.scr.addstr(0, w - len(bc) - 2, f"{bc} ")
            self.scr.attroff(curses.color_pair(6))

    def _draw_tabs(self, w):
        views = [
            ("1", "Podcasts",    self.VIEW_PODCASTS),
            ("2", "In Progress", self.VIEW_QUEUE if self.queue_mode == "in_progress" else None),
            ("3", "New",      self.VIEW_QUEUE if self.queue_mode == "new" else None),
            ("4", "Starred",   self.VIEW_QUEUE if self.queue_mode == "starred" else None),
            ("5", "Files",       self.VIEW_FILES),
        ]
        x = 1
        for key, label, vcheck in views:
            active = (
                (self.view == self.VIEW_PODCASTS and key == "1") or
                (self.view == self.VIEW_EPISODES and key == "1") or
                (self.view == self.VIEW_QUEUE and self.queue_mode == "in_progress" and key == "2") or
                (self.view == self.VIEW_QUEUE and self.queue_mode == "new" and key == "3") or
                (self.view == self.VIEW_QUEUE and self.queue_mode == "starred" and key == "4") or
                (self.view == self.VIEW_FILES and key == "5")
            )
            tag = f"[{key}] {label}"
            if active:
                self.scr.attron(curses.color_pair(2) | curses.A_BOLD)
            else:
                self.scr.attron(curses.color_pair(3))
            try:
                self.scr.addstr(1, x, tag)
            except Exception:
                pass
            if active:
                self.scr.attroff(curses.color_pair(2) | curses.A_BOLD)
            else:
                self.scr.attroff(curses.color_pair(3))
            x += len(tag) + 2

    def _ep_indicator(self, ep):
        stat = ep.get("playingStatus", 0) or 0
        pos  = ep.get("playedUpTo", 0) or 0
        if stat == 3:
            return "●"
        elif pos and int(pos) > 5:
            return "◐"
        return "○"

    def _file_indicator(self, f):
        dur  = int(f.get("duration", 0) or 0)
        pos  = int(f.get("playedUpTo", 0) or 0)
        stat = int(f.get("playingStatus", 0) or 0)
        if stat == 3 or (dur and pos >= dur - 30):
            return "●"
        elif pos > 5:
            return "◐"
        return "○"

    def _file_right(self, f):
        dur  = int(f.get("duration", 0) or 0)
        pos  = int(f.get("playedUpTo", 0) or 0)
        date = fmt_date(f.get("published", f.get("modifiedAt", "")))
        dur_str = fmt_dur(dur)
        if pos > 5:
            return f"{fmt_dur(pos)}/{dur_str}  {date}"
        return f"{dur_str}  {date}"

    def _ep_right(self, ep):
        dur     = ep.get("duration", 0) or 0
        pos     = ep.get("playedUpTo", 0) or 0
        date    = fmt_date(ep.get("publishedAt", ""))
        dur_str = fmt_dur(dur)
        if pos and int(pos) > 5:
            return f"{fmt_dur(pos)}/{dur_str}  {date}"
        return f"{dur_str}  {date}"

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
        ow = min(w - 4, 80)
        oh = min(h - 4, 20)
        ox = (w - ow) // 2
        oy = (h - oh) // 2

        # Background
        for y in range(oh):
            try:
                self.scr.attron(curses.color_pair(4))
                self.scr.addstr(oy + y, ox, " " * ow)
                self.scr.attroff(curses.color_pair(4))
            except Exception:
                pass

        # Border
        title = trunc(ep.get("title", ""), ow - 4)
        self.scr.attron(curses.color_pair(1) | curses.A_BOLD)
        try:
            self.scr.addstr(oy, ox + 2, f" {title} ")
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(1) | curses.A_BOLD)

        # Description with word wrap
        desc = ep.get("description", "No description available.")
        words = desc.split()
        lines = []
        line  = ""
        for word in words:
            if len(line) + len(word) + 1 <= ow - 4:
                line = f"{line} {word}".strip()
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)

        max_lines = oh - 3
        for i, l in enumerate(lines[:max_lines]):
            try:
                self.scr.addstr(oy + 1 + i, ox + 2, trunc(l, ow - 4))
            except Exception:
                pass

        # Close hint
        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(oy + oh - 1, ox + 2, "d / Esc = close")
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

    def _draw_separator(self, y, w, label=""):
        line = "─" * w
        if label:
            mid = (w - len(label)) // 2
            line = "─" * mid + label + "─" * (w - mid - len(label))
        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(y, 0, trunc(line, w))
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

    def _draw_content(self, top, height, w):
        if self.view == self.VIEW_PODCASTS:
            self._draw_list(
                top, height, w,
                items=self.podcasts,
                cursor=self.pod_cursor,
                offset=self.pod_offset,
                fmt=lambda i, p: (
                    trunc(p.get("title", ""), w - 4),
                    ""
                ),
            )
        elif self.view == self.VIEW_EPISODES:
            self._draw_list(
                top, height, w,
                items=self.episodes,
                cursor=self.ep_cursor,
                offset=self.ep_offset,
                fmt=lambda i, ep: (
                    self._ep_indicator(ep) + " " + trunc(ep.get("title", ""), w - 28),
                    self._ep_right(ep),
                ),
            )
        elif self.view == self.VIEW_QUEUE:
            self._draw_list(
                top, height, w,
                items=self.queue_items,
                cursor=self.q_cursor,
                offset=self.q_offset,
                fmt=lambda i, ep: (
                    trunc(ep.get("title", ""), w - 30),
                    f"{trunc(ep.get('podcastTitle',''), 14)}  {fmt_dur(ep.get('playedUpTo',0))}/{fmt_dur(ep.get('duration',0))}",
                ),
            )
        elif self.view == self.VIEW_FILES:
            self._draw_list(
                top, height, w,
                items=self.files_items,
                cursor=self.f_cursor,
                offset=self.f_offset,
                fmt=lambda i, f: (
                    self._file_indicator(f) + " " + trunc(f.get("title", ""), w - 30),
                    self._file_right(f),
                ),
            )

    def _draw_list(self, top, height, w, items, cursor, offset, fmt):
        if not items:
            self.scr.attron(curses.color_pair(3))
            self.scr.addstr(top + 1, 2, "No results.")
            self.scr.attroff(curses.color_pair(3))
            return

        visible = items[offset: offset + height]

        for i, item in enumerate(visible):
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
                    self.scr.attron(curses.color_pair(5) | curses.A_BOLD)
                    self.scr.addstr(y, 0, trunc(line, w))
                    self.scr.attroff(curses.color_pair(5) | curses.A_BOLD)
                else:
                    self.scr.addstr(y, 0, trunc(line, w))
                    # Colorear indicador al inicio del titulo
                    if self.view in (self.VIEW_EPISODES, self.VIEW_FILES):
                        stat = item.get("playingStatus", 0) or 0
                        pos  = item.get("playedUpTo", 0) or 0
                        dur  = int(item.get("duration", 0) or 0)
                        if stat == 3 or (dur and int(pos) >= dur - 30):
                            col = curses.color_pair(2)   # green
                        elif pos and int(pos) > 5:
                            col = curses.color_pair(3)   # yellow
                        else:
                            col = curses.A_DIM
                        self.scr.addstr(y, 1, left[0], col)  # position 1 = indicator
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

    def _draw_player(self, top, w):
        pos  = self.mpv.get_position() if self.mpv.is_running() else 0
        dur  = self.mpv.get_duration() if self.mpv.is_running() else 0
        paus = self.mpv.get_paused()   if self.mpv.is_running() else True
        spd  = self.SPEEDS[self.speed_idx]

        ep_title  = self.playing_ep.get("title", "")  if self.playing_ep  else ""
        pod_title = self.playing_pod.get("title", "") if self.playing_pod else ""

        # Line 1: podcast y episodio
        self.scr.attron(curses.color_pair(1))
        self.scr.addstr(top, 1, trunc(f"♫  {pod_title}", w // 2))
        self.scr.attroff(curses.color_pair(1))
        self.scr.attron(curses.color_pair(4))
        ep_x = w // 2
        self.scr.addstr(top, ep_x, trunc(ep_title, w - ep_x - 1))
        self.scr.attroff(curses.color_pair(4))

        # Line 2: barra de progreso
        if not self.mpv.is_running() and self.playing_ep:
            saved = int(self.playing_ep.get("playedUpTo", 0) or 0)
            state  = "▶"
            times  = f" {fmt_dur(saved)} / {fmt_dur(int(self.playing_ep.get('duration', 0) or 0))} "
            ready  = "  press space to continue"
            self.scr.attron(curses.color_pair(2) | curses.A_BOLD)
            try:
                self.scr.addstr(top + 1, 0, f" {state} {times}")
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(2) | curses.A_BOLD)
            self.scr.attron(curses.color_pair(3))
            try:
                self.scr.addstr(top + 1, 4 + len(times), ready)
            except Exception:
                pass
            self.scr.attroff(curses.color_pair(3))
        else:
            state   = "⏸" if paus else "▶"
            spd_str = f" {spd}x"
            times   = f" {fmt_dur(pos)} / {fmt_dur(dur)} "
            bar_w   = w - len(times) - len(spd_str) - 5
            filled  = int(bar_w * pos / dur) if dur else 0
            bar     = "━" * filled + "─" * max(0, bar_w - filled)

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

        # Line 3: pct completado
        pct = int(pos / dur * 100) if dur else 0
        self.scr.attron(curses.color_pair(3))
        try:
            self.scr.addstr(top + 2, 1, f"{pct}% completado")
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(3))

        # Line 4: controles
        ss_labels = ["", "skip:normal", "skip:medium", "skip:aggressive"]
        ss_str = f"  {ss_labels[self.skip_silence]}" if self.skip_silence else ""
        ctrls = f"space/p=pause  ←/→=±30s  [=slower  ]=faster  S=skip silence{ss_str}  q=salir"
        self.scr.attron(curses.color_pair(8))
        try:
            self.scr.addstr(top + 3, 1, trunc(ctrls, w - 2))
        except Exception:
            pass
        self.scr.attroff(curses.color_pair(8))

    def _draw_footer(self, y, w):
        msg   = self.status_msg
        color = curses.color_pair(7) if getattr(self, "status_error", False) else curses.color_pair(3)
        if msg and time.time() - self.status_timer > 4:
            self.status_msg   = ""
            self.status_error = False
            msg = ""
        if not msg and not (self.mpv.is_running() or self.playing_ep):
            # Mostrar hint de navegacion cuando no hay player
            hints = {
                self.VIEW_PODCASTS:  "↑↓/jk=navigate  Enter=open  q=quit",
                self.VIEW_EPISODES:  "↑↓/jk=navigate  Enter=play  Backspace=back  q=quit",
                self.VIEW_QUEUE:     "↑↓/jk=navigate  Enter=play  q=quit",
                self.VIEW_FILES:     "↑↓/jk=navigate  Enter=play  q=quit",
            }
            msg   = hints.get(self.view, "")
            color = curses.color_pair(3)
        try:
            self.scr.attron(color)
            self.scr.addstr(y, 0, trunc(f" {msg}", w))
            self.scr.attroff(color)
        except Exception:
            pass

    # ── Navigation helpers ────────────────────

    def _scroll(self, cursor, offset, delta, total, visible):
        cursor = max(0, min(total - 1, cursor + delta))
        if cursor < offset:
            offset = cursor
        elif cursor >= offset + visible:
            offset = cursor - visible + 1
        return cursor, offset

    def _visible_rows(self):
        h, _ = self.scr.getmaxyx()
        player_h = 4 if (self.mpv.is_running() or self.playing_ep) else 0
        return h - 3 - player_h - 1  # header + hint + status

    # ── Input handling ────────────────────────

    def handle_key(self, key):
        h, w = self.scr.getmaxyx()
        vis  = self._visible_rows()

        # Global keys
        if key == ord("q") or key == ord("Q"):
            if self.show_desc:
                self.show_desc = False
                return True
            return False  # salir

        if key == 27 or (key == ord("d") and self.show_desc):  # Esc o d cierra overlay
            self.show_desc = False
            return True

        if key == ord("d") and self.view in (self.VIEW_EPISODES, self.VIEW_QUEUE):
            self.show_desc = True
            return True

        if key == ord("1"):
            self.view = self.VIEW_PODCASTS
            if not self.podcasts:
                self.load_podcasts()
            return True

        if key == ord("2"):
            self.view       = self.VIEW_QUEUE
            self.queue_mode = "in_progress"
            self.load_queue()
            return True

        if key == ord("3"):
            self.view       = self.VIEW_QUEUE
            self.queue_mode = "new"
            self.load_queue()
            return True

        if key == ord("4"):
            self.view       = self.VIEW_QUEUE
            self.queue_mode = "starred"
            self.load_queue()
            return True

        if key == ord("5"):
            self.view = self.VIEW_FILES
            if not self.files_items:
                self.load_files()
            return True

        # Controles player (siempre disponibles)
        if key in (ord("p"), ord(" ")):
            if self.mpv.is_running():
                self.mpv.pause_toggle()
            elif self.playing_ep:
                # Arrancar el ultimo episodio cargado
                if self.playing_pod and self.playing_pod.get("uuid") == "__files__":
                    self.play_file(self.playing_ep)
                else:
                    self.play(self.playing_pod or {"uuid": "", "title": ""}, self.playing_ep)
            return True

        if key == curses.KEY_RIGHT and self.mpv.is_running():
            self.mpv.seek(30)
            return True

        if key == curses.KEY_LEFT and self.mpv.is_running():
            self.mpv.seek(-30)
            return True

        if key == ord("]") and self.mpv.is_running():
            self.speed_idx = min(len(self.SPEEDS) - 1, self.speed_idx + 1)
            self.mpv.set_speed(self.SPEEDS[self.speed_idx])
            self.status(f"Speed: {self.SPEEDS[self.speed_idx]}x")
            return True

        if key == ord("[") and self.mpv.is_running():
            self.speed_idx = max(0, self.speed_idx - 1)
            self.mpv.set_speed(self.SPEEDS[self.speed_idx])
            self.status(f"Speed: {self.SPEEDS[self.speed_idx]}x")
            return True

        if key == ord("S") and self.playing_ep:
            self.skip_silence = (self.skip_silence + 1) % 4
            labels = ["off", "normal", "medium", "aggressive"]
            self.status(f"Skip silence: {labels[self.skip_silence]} (applies on next play)")
            return True

        # Podcasts view
        if self.view == self.VIEW_PODCASTS:
            if key == curses.KEY_DOWN or key == ord("j"):
                self.pod_cursor, self.pod_offset = self._scroll(
                    self.pod_cursor, self.pod_offset, 1, len(self.podcasts), vis)
            elif key == curses.KEY_UP or key == ord("k"):
                self.pod_cursor, self.pod_offset = self._scroll(
                    self.pod_cursor, self.pod_offset, -1, len(self.podcasts), vis)
            elif key == curses.KEY_NPAGE:
                self.pod_cursor, self.pod_offset = self._scroll(
                    self.pod_cursor, self.pod_offset, vis, len(self.podcasts), vis)
            elif key == curses.KEY_PPAGE:
                self.pod_cursor, self.pod_offset = self._scroll(
                    self.pod_cursor, self.pod_offset, -vis, len(self.podcasts), vis)
            elif key in (curses.KEY_ENTER, 10, 13):
                if self.podcasts:
                    pod = self.podcasts[self.pod_cursor]
                    self.load_episodes(pod)
                    self.view = self.VIEW_EPISODES

        # Episodes view
        elif self.view == self.VIEW_EPISODES:
            if key == curses.KEY_DOWN or key == ord("j"):
                self.ep_cursor, self.ep_offset = self._scroll(
                    self.ep_cursor, self.ep_offset, 1, len(self.episodes), vis)
            elif key == curses.KEY_UP or key == ord("k"):
                self.ep_cursor, self.ep_offset = self._scroll(
                    self.ep_cursor, self.ep_offset, -1, len(self.episodes), vis)
            elif key == curses.KEY_NPAGE:
                self.ep_cursor, self.ep_offset = self._scroll(
                    self.ep_cursor, self.ep_offset, vis, len(self.episodes), vis)
            elif key == curses.KEY_PPAGE:
                self.ep_cursor, self.ep_offset = self._scroll(
                    self.ep_cursor, self.ep_offset, -vis, len(self.episodes), vis)
            elif key in (curses.KEY_ENTER, 10, 13):
                if self.episodes:
                    ep = self.episodes[self.ep_cursor]
                    self.play(self.current_pod, ep)
            elif key in (curses.KEY_BACKSPACE, 127, ord("b")):
                self.view = self.VIEW_PODCASTS

        # Queue view (in_progress / new / starred)
        elif self.view == self.VIEW_QUEUE:
            if key == curses.KEY_DOWN or key == ord("j"):
                self.q_cursor, self.q_offset = self._scroll(
                    self.q_cursor, self.q_offset, 1, len(self.queue_items), vis)
            elif key == curses.KEY_UP or key == ord("k"):
                self.q_cursor, self.q_offset = self._scroll(
                    self.q_cursor, self.q_offset, -1, len(self.queue_items), vis)
            elif key == curses.KEY_NPAGE:
                self.q_cursor, self.q_offset = self._scroll(
                    self.q_cursor, self.q_offset, vis, len(self.queue_items), vis)
            elif key == curses.KEY_PPAGE:
                self.q_cursor, self.q_offset = self._scroll(
                    self.q_cursor, self.q_offset, -vis, len(self.queue_items), vis)
            elif key in (curses.KEY_ENTER, 10, 13):
                if self.queue_items:
                    ep = self.queue_items[self.q_cursor]
                    pod_uuid = ep.get("podcastUuid") or ep.get("podcast_uuid") or ep.get("podcast")
                    pod = {"uuid": pod_uuid, "title": ep.get("podcastTitle", "")}
                    self.play(pod, ep)

        # Files view
        elif self.view == self.VIEW_FILES:
            if key == curses.KEY_DOWN or key == ord("j"):
                self.f_cursor, self.f_offset = self._scroll(
                    self.f_cursor, self.f_offset, 1, len(self.files_items), vis)
            elif key == curses.KEY_UP or key == ord("k"):
                self.f_cursor, self.f_offset = self._scroll(
                    self.f_cursor, self.f_offset, -1, len(self.files_items), vis)
            elif key == curses.KEY_NPAGE:
                self.f_cursor, self.f_offset = self._scroll(
                    self.f_cursor, self.f_offset, vis, len(self.files_items), vis)
            elif key == curses.KEY_PPAGE:
                self.f_cursor, self.f_offset = self._scroll(
                    self.f_cursor, self.f_offset, -vis, len(self.files_items), vis)
            elif key in (curses.KEY_ENTER, 10, 13):
                if self.files_items:
                    self.play_file(self.files_items[self.f_cursor])

        return True

    # ── Main loop ─────────────────────────────

    def _load_last_played(self):
        """Load last played episode/file on startup, shown as ready to play"""
        try:
            # Latest in progress (podcasts) - usar playedUpToModified como timestamp
            in_prog = self.api.in_progress()
            last_ep = in_prog[0] if in_prog else None

            # Latest files played
            files = self.api.files()
            self.files_items = files
            with_progress = [f for f in files if (f.get("playedUpTo") or 0) > 5]
            last_file = sorted(
                with_progress,
                key=lambda f: f.get("modifiedAt", ""),
                reverse=True,
            )
            last_file = last_file[0] if last_file else None

            # Comparar por timestamp: episodios usan playedUpToModified (ms epoch string)
            def ts(x):
                if not x:
                    return 0
                # files tienen ISO date, episodios tienen ms epoch
                mod = x.get("modifiedAt") or x.get("playedUpToModified", "0")
                try:
                    if "T" in str(mod):  # ISO date de file
                        from datetime import datetime
                        return datetime.fromisoformat(mod.replace("Z", "+00:00")).timestamp()
                    return int(mod) / 1000  # ms epoch de episodio
                except Exception:
                    return 0

            if last_ep and last_file:
                recent = last_file if ts(last_file) > ts(last_ep) else last_ep
            else:
                recent = last_ep or last_file

            if not recent:
                return

            # Is it a file or episode?
            file_uuids = {f.get("uuid") for f in files}
            if recent.get("uuid") in file_uuids:
                self.playing_pod = {"uuid": "__files__", "title": "Files"}
                self.playing_ep  = recent
            else:
                pod_uuid  = recent.get("podcastUuid") or recent.get("podcast_uuid") or recent.get("podcast", "")
                pod_title = recent.get("podcastTitle", "")
                self.playing_pod = {"uuid": pod_uuid, "title": pod_title}
                self.playing_ep  = recent

            self.status(f"Last played: {recent.get('title', '')[:50]}")
        except Exception as e:
            self.status(f"last_played error: {e}", error=True)

    def run(self):
        self.load_podcasts()
        self._load_last_played()

        # Debug: log playing_ep state
        import os
        with open("/tmp/pocketcli_debug.txt", "w") as f:
            f.write(f"playing_ep: {self.playing_ep}\n")
            f.write(f"playing_pod: {self.playing_pod}\n")

        tick = 0
        while True:
            self.draw()

            # Sync periodico
            self.sync_position()
            self.check_finished()

            # Input (non-blocking, 100ms)
            self.scr.timeout(100)
            key = self.scr.getch()
            if key != -1:
                if not self.handle_key(key):
                    break

            tick += 1

        # Cleanup on exit
        if self.mpv.is_running():
            pos = self.mpv.get_position()
            if self.playing_pod and self.playing_ep:
                self.api.update_position(
                    self.playing_pod["uuid"], self.playing_ep["uuid"], pos
                )
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
            print(f"Error de login: {err}")
            sys.exit(1)

    api = API(token)
    app = PocketTUI(stdscr, api)
    app.run()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
