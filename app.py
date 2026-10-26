import os
import subprocess
import threading
import time
import json
from datetime import datetime

# Automatically install Chromium if on Linux (Hugging Face Spaces)
if os.name != "nt":
    try:
        subprocess.run(["playwright", "install", "chromium"], check=False)
    except Exception as e:
        print("Playwright install check:", e)

from state_manager import StateManager
from spotify_scraper import SpotifyScraper
from telegram_notifier import TelegramNotifier
from telegram_bot_manager import TelegramBotManager
from main import run_all_checks, load_config
import gradio as gr

state_mgr = StateManager("playlist_state.json")
config = load_config("config.json")
playlist_urls = config.get("spotify_playlists", [])
bot_token = config.get("telegram_bot_token", "")
chat_id = config.get("telegram_chat_id", "")
interval = config.get("check_interval_seconds", 60)

notifier = TelegramNotifier(bot_token, chat_id)
scraper = SpotifyScraper()

# Start Telegram Bot Manager in background
bot_manager = TelegramBotManager(
    bot_token,
    chat_id,
    state_mgr,
    on_check_now=lambda: run_all_checks(scraper, state_mgr, notifier, playlist_urls)
)
if notifier.is_configured:
    bot_manager.start()

# Monitor loop in background thread
def monitor_loop():
    time.sleep(5)
    while True:
        try:
            run_all_checks(scraper, state_mgr, notifier, playlist_urls)
        except Exception as e:
            print("Monitor loop error:", e)
        time.sleep(interval)

monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

def get_dashboard_data():
    summary = state_mgr.get_all_playlists_summary()
    total_tracks = sum(p.get("total_tracks", 0) for p in summary)

    today_changes = state_mgr.get_changes_today()
    today_lines = []
    for pid, pinfo in today_changes.items():
        for a in pinfo.get("added", []):
            today_lines.append(f"📁 {pinfo['playlist_title']}: 🟢 {a['track_title']} - {a['track_artist']} ({a.get('datetime', '')})")

    week_changes = state_mgr.get_changes_week()
    week_lines = []
    for pid, pinfo in week_changes.items():
        for a in pinfo.get("added", []):
            week_lines.append(f"📁 {pinfo['playlist_title']}: 🟢 {a['track_title']} - {a['track_artist']} ({a.get('datetime', '')})")

    status_text = (
        f"### 🟢 Status: Active & Monitoring 24/7\n"
        f"- **Λίστες σε παρακολούθηση:** {len(summary)} λίστες\n"
        f"- **Συνολικά τραγούδια:** {total_tracks:,} τραγούδια\n"
        f"- **Συχνότητα ελέγχου:** Κάθε {interval} δευτερόλεπτα\n"
        f"- **Telegram Bot:** @listsongsssbot (Ενεργό)"
    )

    today_text = "\n".join(today_lines) if today_lines else "ℹ️ Δεν έχουν προστεθεί νέα τραγούδια σήμερα."
    week_text = "\n".join(week_lines) if week_lines else "ℹ️ Δεν έχουν προστεθεί νέα τραγούδια τις τελευταίες 7 ημέρες."

    return status_text, today_text, week_text

def manual_check():
    run_all_checks(scraper, state_mgr, notifier, playlist_urls)
    return get_dashboard_data()

with gr.Blocks(title="Spotify Playlist Monitor", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🎵 Spotify Multi-Playlist Monitor & Telegram Bot")

    with gr.Row():
        status_md = gr.Markdown()

    with gr.Row():
        check_btn = gr.Button("🔄 Άμεσος Έλεγχος Τώρα (Check Now)", variant="primary")

    with gr.Row():
        with gr.Column():
            gr.Markdown("### 📅 Προσθήκες Σήμερα")
            today_box = gr.Textbox(lines=6, label="Σήμερα", interactive=False)
        with gr.Column():
            gr.Markdown("### 🗓️ Προσθήκες Τελευταίας Εβδομάδας")
            week_box = gr.Textbox(lines=6, label="Τελευταία Εβδομάδα", interactive=False)

    check_btn.click(manual_check, outputs=[status_md, today_box, week_box])
    demo.load(get_dashboard_data, outputs=[status_md, today_box, week_box])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
