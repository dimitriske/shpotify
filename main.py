import argparse
import atexit
import json
import logging
import os
import sys
import time
from datetime import datetime

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console(legacy_windows=False)
    HAS_RICH = True
except Exception:
    HAS_RICH = False
    console = None

from spotify_scraper import SpotifyScraper
from state_manager import StateManager
from telegram_notifier import TelegramNotifier
from telegram_bot_manager import TelegramBotManager
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SpotifyMonitor")

class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Spotify Monitor</title></head>"
            "<body style='font-family: sans-serif; background: #121212; color: #1DB954; text-align: center; padding: 60px;'>"
            "<h1>🎵 Spotify Playlist Monitor</h1>"
            "<p style='color: #ffffff; font-size: 1.3rem;'>Status: 🟢 <b>Active & Monitoring 27 Playlists</b></p>"
            "<p style='color: #b3b3b3;'>Telegram Bot: <b>@listsongsssbot</b></p>"
            "</body></html>"
        )
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass

def start_status_server(port: int = 7860):
    try:
        server = HTTPServer(("0.0.0.0", port), StatusHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        logger.info(f"Web Status Dashboard ενεργό στο port {port}")
    except Exception as e:
        logger.warning(f"Status Web Server δεν εκκίνησε στο port {port}: {e}")


def load_config(config_path: str = "config.json") -> dict:
    cfg = {
        "spotify_playlists": [],
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "check_interval_seconds": 60,
        "notify_on_start": True
    }
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    # Allow Environment variables (e.g. on Render)
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        cfg["telegram_bot_token"] = os.environ.get("TELEGRAM_BOT_TOKEN")
    if os.environ.get("TELEGRAM_CHAT_ID"):
        cfg["telegram_chat_id"] = os.environ.get("TELEGRAM_CHAT_ID")
    return cfg


def print_banner(playlist_count: int, total_tracks: int, interval: int, telegram_configured: bool):
    if HAS_RICH and console:
        table = Table(show_header=False, box=None)
        table.add_row("[bold cyan]📁 Λίστες Spotify:[/bold cyan]", f"[bold white]{playlist_count} λίστες σε παρακολούθηση[/bold white]")
        table.add_row("[bold cyan]🎶 Συνολικά Τραγούδια:[/bold cyan]", f"[bold green]{total_tracks:,}[/bold green]")
        table.add_row("[bold cyan]⏱️ Συχνότητα Ελέγχου:[/bold cyan]", f"Κάθε {interval} δευτερόλεπτα")
        tg_status = "[bold green]Ενεργό (με Διαδραστικό Μενού)[/bold green]" if telegram_configured else "[bold yellow]Ανενεργό (Συμπληρώστε το config.json)[/bold yellow]"
        table.add_row("[bold cyan]🔔 Telegram Bot:[/bold cyan]", tg_status)

        console.print(Panel(
            table,
            title="[bold green]🎵 Spotify Multi-Playlist Monitor (No-API) 🎵[/bold green]",
            border_style="green",
            padding=(1, 2)
        ))
    else:
        print("=" * 60)
        print(f"🎵 Spotify Multi-Playlist Monitor: {playlist_count} λίστες σε παρακολούθηση")
        print(f"🎶 Συνολικά Τραγούδια: {total_tracks}")
        print(f"⏱️ Συχνότητα: Κάθε {interval} δευτερόλεπτα")
        print(f"🔔 Telegram: {'Ενεργό' if telegram_configured else 'Ανενεργό'}")
        print("=" * 60)

def run_all_checks(scraper: SpotifyScraper, state_mgr: StateManager, notifier: TelegramNotifier, playlist_urls: list) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        playlists_data = scraper.fetch_playlists_batch(playlist_urls)
    except Exception as e:
        logger.error(f"[{now_str}] Σφάλμα κατά τη μαζική ανάκτηση λιστών: {e}")
        return

    for current_data in playlists_data:
        pid = current_data["id"]
        title = current_data["title"]
        fetch_error = current_data.get("fetch_error", False)

        # Shield 1: Skip if scraper reported fetch error
        if fetch_error:
            logger.warning(f"[{now_str}] [{title}] Σφάλμα ανάκτησης από Spotify. Αγνοείται για αποφυγή ψευδών διαγραφών.")
            continue

        saved_state = state_mgr.load_playlist_state(pid)

        # First run for this specific playlist
        if saved_state is None:
            if len(current_data["tracks"]) > 0:
                state_mgr.save_playlist_state(current_data)
                logger.info(f"[{now_str}] Αρχικοποίηση '{title}': {len(current_data['tracks'])} τραγούδια.")
            continue

        old_tracks = saved_state.get("tracks", [])
        new_tracks = current_data["tracks"]

        # Shield 2: If new_tracks is 0 but we had tracks, NEVER treat as removal (network glitch)
        if len(new_tracks) == 0 and len(old_tracks) > 0:
            logger.warning(f"[{now_str}] [{title}] Λήφθηκαν 0 τραγούδια (προηγουμένως: {len(old_tracks)}). Προστασία αποφυγής ψευδών διαγραφών.")
            continue

        added, removed = state_mgr.diff_tracks(old_tracks, new_tracks)

        # Shield 3: Mass deletion anomaly shield (no user deletes 70%+ of a playlist in 60s)
        if len(removed) >= len(old_tracks) * 0.7 and len(old_tracks) > 3:
            logger.warning(f"[{now_str}] [{title}] Ανιχνεύθηκε μαζική απώλεια {len(removed)}/{len(old_tracks)} τραγουδιών. Αγνοείται ως ανωμαλία δικτύου.")
            continue

        if not added and not removed:
            continue


        # Notifications
        if added:
            logger.info(f"[{now_str}] [{title}] ➕ {len(added)} νέο/α τραγούδι/α!")
            for t in added:
                logger.info(f"   [+] {t['title']} - {t['artist']}")
            if notifier.is_configured:
                notifier.notify_tracks_added(title, added, current_data["url"])

        if removed:
            logger.info(f"[{now_str}] [{title}] ➖ {len(removed)} διαγραμμένο/α τραγούδι/α!")
            for t in removed:
                logger.info(f"   [-] {t['title']} - {t['artist']}")
            if notifier.is_configured:
                notifier.notify_tracks_removed(title, removed)

        # Update state and history log immediately
        state_mgr.save_playlist_state(current_data, added_tracks=added, removed_tracks=removed)

    logger.info(f"[{now_str}] Έλεγχος ολοκληρώθηκε για {len(playlists_data)} λίστες.")

def sync_user_playlists(user_url: str) -> list:
    logger.info(f"Ανάκτηση λιστών από το προφίλ: {user_url}...")
    import re
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(user_url, timeout=30000)
        page.wait_for_timeout(3000)
        content = page.content()
        pids = list(dict.fromkeys(re.findall(r"/playlist/([a-zA-Z0-9]{22})", content)))
        browser.close()

    urls = [f"https://open.spotify.com/playlist/{pid}" for pid in pids]
    logger.info(f"Βρέθηκαν {len(urls)} λίστες!")
    return urls

def main():
    parser = argparse.ArgumentParser(description="Spotify Multi-Playlist Telegram Monitor")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--interval", type=int, help="Override check interval in seconds")
    parser.add_argument("--check-once", action="store_true", help="Run a single check and exit")
    parser.add_argument("--test-telegram", action="store_true", help="Test Telegram Bot credentials and exit")
    parser.add_argument("--sync-user", help="Sync all playlists from a Spotify user profile URL")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.sync_user:
        urls = sync_user_playlists(args.sync_user)
        config["spotify_playlists"] = urls
        config["spotify_user_url"] = args.sync_user
        with open(args.config, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"✅ Αποθηκεύτηκαν {len(urls)} λίστες στο {args.config}!")
        sys.exit(0)

    playlist_urls = config.get("spotify_playlists", [])
    if not playlist_urls and config.get("spotify_playlist_url"):
        playlist_urls = [config["spotify_playlist_url"]]

    if not playlist_urls:
        logger.error("Δεν έχουν οριστεί λίστες στο config.json (spotify_playlists).")
        sys.exit(1)

    bot_token = config.get("telegram_bot_token", "")
    chat_id = config.get("telegram_chat_id", "")
    interval = args.interval or config.get("check_interval_seconds", 60)

    notifier = TelegramNotifier(bot_token, chat_id)
    scraper = SpotifyScraper()
    state_mgr = StateManager()

    atexit.register(scraper.close)

    if args.test_telegram:
        print("Δοκιμή σύνδεσης με Telegram...")
        res = notifier.test_connection()
        if res.get("ok"):
            print(f"✅ Επιτυχία! Συνδέθηκε στο Bot @{res.get('bot_username')}")
        else:
            print(f"❌ Σφάλμα: {res.get('error')}")
        sys.exit(0)

    # Start interactive Telegram Bot Manager
    bot_manager = TelegramBotManager(
        bot_token,
        chat_id,
        state_mgr,
        on_check_now=lambda: run_all_checks(scraper, state_mgr, notifier, playlist_urls)
    )
    if notifier.is_configured:
        bot_manager.start()

    # Pre-index tracks count
    all_states = state_mgr._load_all()
    total_tracks = sum(s.get("total_tracks", 0) for s in all_states.values() if isinstance(s, dict))

    # Start web status server for Hugging Face Spaces (port 7860)
    web_port = int(os.environ.get("PORT", os.environ.get("SPACE_PORT", 7860)))
    start_status_server(web_port)

    print_banner(len(playlist_urls), total_tracks, interval, notifier.is_configured)

    if args.check_once:
        run_all_checks(scraper, state_mgr, notifier, playlist_urls)
        scraper.close()
        return

    logger.info("Έναρξη παρακολούθησης όλων των λιστών... (Πατήστε Ctrl+C για έξοδο)")
    run_all_checks(scraper, state_mgr, notifier, playlist_urls)

    try:
        while True:
            time.sleep(interval)
            run_all_checks(scraper, state_mgr, notifier, playlist_urls)
    except KeyboardInterrupt:
        bot_manager.stop()
        scraper.close()
        print("\n\n👋 Ο τερματισμός της παρακολούθησης ολοκληρώθηκε.")

if __name__ == "__main__":
    main()
