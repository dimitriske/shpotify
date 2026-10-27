import logging
import threading
import time
from typing import Dict, Any, List, Optional, Callable
import requests

logger = logging.getLogger("TelegramBotManager")

class TelegramBotManager:
    """
    Διαχειρίζεται το διαδραστικό μενού του Telegram Bot (κουμπιά, callbacks, αναζήτηση).
    Λειτουργεί σε background thread χωρίς να καθυστερεί την παρακολούθηση.
    """

    def __init__(self, bot_token: str, chat_id: str, state_mgr, on_check_now: Optional[Callable] = None):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.state_mgr = state_mgr
        self.on_check_now = on_check_now
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if not self.bot_token or not self.chat_id or self.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
            logger.warning("Telegram bot credentials not configured for interactive listener.")
            return
        self.running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Telegram interactive listener started.")

    def stop(self):
        self.running = False

    def send_menu(self, chat_id: Optional[str] = None):
        target_chat = chat_id or self.chat_id
        summary = self.state_mgr.get_all_playlists_summary()
        total_songs = sum(p.get("total_tracks", 0) for p in summary)

        text = (
            "🎵 <b>Spotify Playlist Monitor</b>\n"
            f"📊 <b>Παρακολουθούνται:</b> {len(summary)} λίστες ({total_songs:,} τραγούδια)\n\n"
            "Επιλέξτε μία ενέργεια από το μενού:"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔍 Σήμερα (Όλες οι λίστες)", "callback_data": "today_all"},
                    {"text": "📅 Τελευταία Εβδομάδα (Όλες)", "callback_data": "week_all"},
                ],
                [
                    {"text": "📋 Επιλογή Συγκεκριμένης Λίστας", "callback_data": "pl_page_0"},
                ],
                [
                    {"text": "🔄 Άμεσος Έλεγχος Τώρα", "callback_data": "check_now"},
                ]
            ]
        }
        self._post("sendMessage", {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard
        })

    def _post(self, method: str, payload: dict) -> dict:
        try:
            r = requests.post(f"{self.base_url}/{method}", json=payload, timeout=12)
            return r.json()
        except Exception as e:
            logger.error(f"Telegram API call error ({method}): {e}")
            return {"ok": False}

    def _answer_callback(self, callback_id: str, text: Optional[str] = None):
        payload = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        self._post("answerCallbackQuery", payload)

    def _edit_message(self, chat_id: str, message_id: int, text: str, keyboard: Optional[dict] = None):
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if keyboard:
            payload["reply_markup"] = keyboard
        self._post("editMessageText", payload)

    def _poll_loop(self):
        offset = 0
        while self.running:
            try:
                res = requests.get(
                    f"{self.base_url}/getUpdates",
                    params={"offset": offset, "timeout": 20},
                    timeout=25
                ).json()

                if not res.get("ok"):
                    time.sleep(2)
                    continue

                for update in res.get("result", []):
                    offset = update["update_id"] + 1

                    if "message" in update:
                        msg = update["message"]
                        cid = str(msg.get("chat", {}).get("id", ""))
                        raw_text = msg.get("text", "").strip()
                        text_lower = raw_text.lower()

                        # Matches: menu, Menu, MENU, μενού, ΜΕΝΟΥ, /menu, /start, etc.
                        is_menu = (
                            text_lower in ["/start", "/menu", "menu", "μενού", "μενου", "λίστες", "λιστες", "start", "help", "βοήθεια"]
                            or "menu" in text_lower
                            or "μενού" in text_lower
                            or "μενου" in text_lower
                            or text_lower.startswith("/")
                            or bool(text_lower)
                        )
                        if is_menu:
                            self.send_menu(cid)


                    elif "callback_query" in update:
                        cq = update["callback_query"]
                        cb_id = cq["id"]
                        cb_data = cq.get("data", "")
                        msg = cq.get("message", {})
                        cid = str(msg.get("chat", {}).get("id", ""))
                        mid = msg.get("message_id")

                        self._handle_callback(cb_id, cb_data, cid, mid)

            except Exception as e:
                time.sleep(2)

    def _handle_callback(self, cb_id: str, data: str, chat_id: str, message_id: int):
        self._answer_callback(cb_id)

        if data == "menu_main":
            summary = self.state_mgr.get_all_playlists_summary()
            total_songs = sum(p.get("total_tracks", 0) for p in summary)
            text = (
                "🎵 <b>Spotify Playlist Monitor</b>\n"
                f"📊 <b>Παρακολουθούνται:</b> {len(summary)} λίστες ({total_songs:,} τραγούδια)\n\n"
                "Επιλέξτε μία ενέργεια:"
            )
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🔍 Σήμερα (Όλες οι λίστες)", "callback_data": "today_all"},
                        {"text": "📅 Τελευταία Εβδομάδα (Όλες)", "callback_data": "week_all"},
                    ],
                    [
                        {"text": "📋 Επιλογή Συγκεκριμένης Λίστας", "callback_data": "pl_page_0"},
                    ],
                    [
                        {"text": "🔄 Άμεσος Έλεγχος Τώρα", "callback_data": "check_now"},
                    ]
                ]
            }
            self._edit_message(chat_id, message_id, text, keyboard)

        elif data == "today_all":
            changes = self.state_mgr.get_changes_today()
            if not changes:
                text = (
                    "📅 <b>Έλεγχος Σήμερα</b>\n\n"
                    "ℹ️ <i>Δεν έχουν καταγραφεί νέες προσθήκες τραγουδιών σήμερα στις λίστες.</i>\n\n"
                    "Το bot συνεχίζει να παρακολουθεί αυτόματα!"
                )
            else:
                lines = ["📅 <b>Τραγούδια που προστέθηκαν σήμερα:</b>\n"]
                for pid, pinfo in changes.items():
                    title = pinfo["playlist_title"]
                    added = pinfo.get("added", [])
                    if added:
                        lines.append(f"📁 <b>{title}</b> ({len(added)} νέα):")
                        for a in added:
                            dt = a.get("datetime", "").split(" ")[-1]
                            lines.append(f"   • 🟢 <b>{a['track_title']}</b> – {a['track_artist']} <i>({dt})</i>")
                        lines.append("")
                text = "\n".join(lines)
                if len(text) > 4000:
                    text = text[:3950] + "\n\n<i>...και άλλα τραγούδια</i>"

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Πίσω στο Μενού", "callback_data": "menu_main"}]
                ]
            }
            self._edit_message(chat_id, message_id, text, keyboard)

        elif data == "week_all":
            changes = self.state_mgr.get_changes_week()
            if not changes:
                text = (
                    "📅 <b>Έλεγχος Τελευταίας Εβδομάδας (7 Ημέρες)</b>\n\n"
                    "ℹ️ <i>Δεν έχουν καταγραφεί νέες προσθήκες τις τελευταίες 7 ημέρες σε καμία λίστα.</i>"
                )
            else:
                lines = ["📅 <b>Τραγούδια τελευταίας εβδομάδας (7 Ημέρες):</b>\n"]
                for pid, pinfo in changes.items():
                    title = pinfo["playlist_title"]
                    added = pinfo.get("added", [])
                    if added:
                        lines.append(f"📁 <b>{title}</b> ({len(added)} νέα):")
                        for a in added:
                            dt = a.get("datetime", "")
                            lines.append(f"   • 🟢 <b>{a['track_title']}</b> – {a['track_artist']} <i>({dt})</i>")
                        lines.append("")
                text = "\n".join(lines)
                if len(text) > 4000:
                    text = text[:3950] + "\n\n<i>...και άλλα τραγούδια</i>"

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Πίσω στο Μενού", "callback_data": "menu_main"}]
                ]
            }
            self._edit_message(chat_id, message_id, text, keyboard)

        elif data.startswith("pl_page_"):
            page = int(data.split("_")[-1])
            playlists = self.state_mgr.get_all_playlists_summary()
            per_page = 6
            total_pages = (len(playlists) + per_page - 1) // per_page
            page = max(0, min(page, total_pages - 1))

            start_idx = page * per_page
            page_items = playlists[start_idx : start_idx + per_page]

            text = (
                f"📋 <b>Επιλογή Λίστας</b> (Σελίδα {page + 1} από {total_pages})\n\n"
                "Επιλέξτε μία λίστα για να δείτε τα τραγούδια της:"
            )

            btn_rows = []
            for pl in page_items:
                title = pl["title"]
                total = pl["total_tracks"]
                btn_rows.append([
                    {"text": f"📁 {title} ({total})", "callback_data": f"pl_view_{pl['id']}"}
                ])

            # Navigation row
            nav_row = []
            if page > 0:
                nav_row.append({"text": "◀ Προηγ.", "callback_data": f"pl_page_{page - 1}"})
            nav_row.append({"text": f"{page + 1}/{total_pages}", "callback_data": "noop"})
            if page < total_pages - 1:
                nav_row.append({"text": "Επόμ. ▶", "callback_data": f"pl_page_{page + 1}"})
            btn_rows.append(nav_row)

            btn_rows.append([{"text": "🔙 Πίσω στο Μενού", "callback_data": "menu_main"}])

            keyboard = {"inline_keyboard": btn_rows}
            self._edit_message(chat_id, message_id, text, keyboard)

        elif data.startswith("pl_view_"):
            pid = data.split("_")[-1]
            pl = self.state_mgr.load_playlist_state(pid)
            if not pl:
                self._edit_message(chat_id, message_id, "❌ Η λίστα δεν βρέθηκε.", None)
                return

            title = pl.get("playlist_title", "Λίστα")
            author = pl.get("playlist_author", "Δημιουργός")
            tracks = pl.get("tracks", [])

            # Get today & week changes
            today_changes = self.state_mgr.get_changes_today(pid)
            week_changes = self.state_mgr.get_changes_week(pid)

            added_today = len(today_changes.get(pid, {}).get("added", []))
            added_week = len(week_changes.get(pid, {}).get("added", []))

            text = (
                f"📁 <b>Λίστα: {title}</b>\n"
                f"👤 <b>Δημιουργός:</b> {author}\n"
                f"🎶 <b>Σύνολο Τραγουδιών:</b> {len(tracks)}\n\n"
                f"🟢 <b>Προστέθηκαν σήμερα:</b> {added_today} τραγούδια\n"
                f"📅 <b>Προστέθηκαν τις τελευταίες 7 ημέρες:</b> {added_week} τραγούδια\n"
            )

            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🔍 Τραγούδια Σήμερα", "callback_data": f"pl_today_{pid}"},
                        {"text": "📅 Τραγούδια Εβδομάδας", "callback_data": f"pl_week_{pid}"},
                    ],
                    [
                        {"text": "📜 Τελευταία Τραγούδια (με Ημερομηνίες)", "callback_data": f"pl_recent_{pid}"},
                    ],
                    [
                        {"text": "🔙 Πίσω στις Λίστες", "callback_data": "pl_page_0"},
                        {"text": "🏠 Αρχικό Μενού", "callback_data": "menu_main"},
                    ]
                ]
            }
            self._edit_message(chat_id, message_id, text, keyboard)

        elif data.startswith("pl_today_") or data.startswith("pl_week_"):
            is_week = data.startswith("pl_week_")
            pid = data.split("_")[-1]
            pl = self.state_mgr.load_playlist_state(pid)
            title = pl.get("playlist_title", "Λίστα") if pl else "Λίστα"

            changes = self.state_mgr.get_changes_week(pid) if is_week else self.state_mgr.get_changes_today(pid)
            items = changes.get(pid, {}).get("added", [])

            label = "τις τελευταίες 7 ημέρες" if is_week else "σήμερα"
            if not items:
                text = f"📁 <b>{title}</b>\n\nℹ️ <i>Δεν προστέθηκαν τραγούδια {label}.</i>"
            else:
                lines = [f"📁 <b>{title}</b> – Προσθήκες {label} ({len(items)}):\n"]
                for item in items:
                    dt = item.get("datetime", "")
                    lines.append(f"• 🟢 <b>{item['track_title']}</b> – {item['track_artist']}\n  🕒 <i>{dt}</i>")
                text = "\n".join(lines)

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Πίσω στη Λίστα", "callback_data": f"pl_view_{pid}"}]
                ]
            }
            self._edit_message(chat_id, message_id, text, keyboard)

        elif data.startswith("pl_recent_"):
            pid = data.split("_")[-1]
            pl = self.state_mgr.load_playlist_state(pid)
            title = pl.get("playlist_title", "Λίστα") if pl else "Λίστα"
            tracks = pl.get("tracks", []) if pl else []

            # Show last 10 tracks
            recent_tracks = tracks[-10:] if len(tracks) > 10 else tracks
            recent_tracks = list(reversed(recent_tracks))

            lines = [f"📁 <b>{title}</b> – Τελευταία {len(recent_tracks)} Τραγούδια:\n"]
            for idx, t in enumerate(recent_tracks, 1):
                added_str = t.get("added_at", "Άγνωστη ημερομηνία")
                url = t.get("url", "")
                name = t.get("title", "")
                artist = t.get("artist", "")
                if url:
                    lines.append(f"<b>{idx}.</b> <a href=\"{url}\">{name}</a> – {artist}\n   🕒 <i>Προστέθηκε: {added_str}</i>")
                else:
                    lines.append(f"<b>{idx}.</b> {name} – {artist}\n   🕒 <i>Προστέθηκε: {added_str}</i>")

            text = "\n".join(lines)
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Πίσω στη Λίστα", "callback_data": f"pl_view_{pid}"}]
                ]
            }
            self._edit_message(chat_id, message_id, text, keyboard)

        elif data == "check_now":
            self._edit_message(chat_id, message_id, "⏳ <b>Εκτελείται άμεσος έλεγχος και στις 27 λίστες...</b> Παρακαλώ περιμένετε.")
            if self.on_check_now:
                try:
                    self.on_check_now()
                    res_text = "✅ <b>Ο άμεσος έλεγχος ολοκληρώθηκε επιτυχώς!</b>\nΑν υπήρξαν αλλαγές, εστάλησαν ήδη οι ειδοποιήσεις."
                except Exception as e:
                    res_text = f"❌ Σφάλμα κατά τον έλεγχο: {e}"
            else:
                res_text = "✅ Ολοκληρώθηκε."

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Πίσω στο Μενού", "callback_data": "menu_main"}]
                ]
            }
            self._edit_message(chat_id, message_id, res_text, keyboard)
