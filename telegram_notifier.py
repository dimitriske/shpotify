import logging
from typing import Dict, Any, List, Optional
import requests

logger = logging.getLogger("TelegramNotifier")

class TelegramNotifier:
    """
    Sends notifications to a Telegram chat or channel via Telegram Bot API.
    """

    def __init__(self, bot_token: str, chat_id: str, timeout: int = 10):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.timeout = timeout
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and self.bot_token != "YOUR_TELEGRAM_BOT_TOKEN")

    def send_message(self, text: str, parse_mode: str = "HTML", disable_web_page_preview: bool = False) -> bool:
        if not self.is_configured:
            logger.warning("Telegram Bot Token or Chat ID is not configured. Notification skipped.")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }

        try:
            res = requests.post(url, json=payload, timeout=self.timeout)
            data = res.json()
            if not data.get("ok"):
                logger.error(f"Telegram API error: {data.get('description')}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """
        Validates token using getMe and sends a test ping.
        """
        if not self.is_configured:
            return {"ok": False, "error": "Bot token or Chat ID is missing."}

        try:
            me_res = requests.get(f"{self.base_url}/getMe", timeout=self.timeout).json()
            if not me_res.get("ok"):
                return {"ok": False, "error": f"Invalid Bot Token: {me_res.get('description')}"}
            bot_username = me_res["result"]["username"]

            test_text = (
                f"✅ <b>Δοκιμαστικό μήνυμα επιτυχές!</b>\n"
                f"🤖 Bot: @{bot_username}\n"
                f"🔔 Η σύνδεση του Spotify Monitor με το Telegram λειτουργεί κανονικά."
            )
            sent = self.send_message(test_text)
            if sent:
                return {"ok": True, "bot_username": bot_username}
            else:
                return {"ok": False, "error": "Could not send message to Chat ID. Ensure you sent /start to the bot."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def notify_started(self, playlist_title: str, playlist_author: str, track_count: int, playlist_url: str) -> bool:
        text = (
            f"🚀 <b>Spotify Playlist Monitor ενεργοποιήθηκε!</b>\n\n"
            f"📁 <b>Λίστα:</b> <a href=\"{playlist_url}\">{playlist_title}</a>\n"
            f"👤 <b>Δημιουργός:</b> {playlist_author}\n"
            f"🎶 <b>Αρχικός αριθμός τραγουδιών:</b> {track_count}\n\n"
            f"<i>Θα λαμβάνετε ειδοποίηση κάθε φορά που προστίθεται ή αφαιρείται τραγούδι.</i>"
        )
        return self.send_message(text, disable_web_page_preview=True)

    def notify_tracks_added(self, playlist_title: str, tracks: List[Dict[str, Any]], playlist_url: str) -> None:
        count = len(tracks)
        header = f"✨ <b>Προστέθηκε {count} νέο τραγούδι!</b>\n📁 <b>Λίστα:</b> {playlist_title}\n\n" if count == 1 else f"✨ <b>Προστέθηκαν {count} νέα τραγούδια!</b>\n📁 <b>Λίστα:</b> {playlist_title}\n\n"

        items = []
        for t in tracks:
            title = t.get("title", "Χωρίς τίτλο")
            artist = t.get("artist", "Άγνωστος")
            url = t.get("url", "")
            if url:
                items.append(f"🟢 <b>{title}</b>\n   👤 {artist}\n   🔗 <a href=\"{url}\">Άνοιγμα στο Spotify</a>")
            else:
                items.append(f"🟢 <b>{title}</b>\n   👤 {artist}")

        text = header + "\n\n".join(items)
        self.send_message(text, disable_web_page_preview=True)

    def notify_tracks_removed(self, playlist_title: str, tracks: List[Dict[str, Any]]) -> None:
        count = len(tracks)
        header = f"🗑️ <b>Αφαιρέθηκε {count} τραγούδι!</b>\n📁 <b>Λίστα:</b> {playlist_title}\n\n" if count == 1 else f"🗑️ <b>Αφαιρέθηκαν {count} τραγούδια!</b>\n📁 <b>Λίστα:</b> {playlist_title}\n\n"

        items = []
        for t in tracks:
            title = t.get("title", "Χωρίς τίτλο")
            artist = t.get("artist", "Άγνωστος")
            items.append(f"🔴 <b>{title}</b>\n   👤 {artist}")

        text = header + "\n\n".join(items)
        self.send_message(text, disable_web_page_preview=True)
