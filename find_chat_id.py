import sys
import time
import json
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def main():
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    bot_token = config.get("telegram_bot_token", "").strip()
    if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        print("❌ Παρακαλώ εισάγετε πρώτα το Telegram Bot Token στο config.json.")
        return

    print("=" * 65)
    print("🤖 Αυτόματος εντοπισμός Telegram Chat ID")
    print("=" * 65)
    print("Βήμα 1: Ανοίξτε το Telegram και αναζητήστε το bot σας: @listsongsssbot")
    print("        ή κάντε κλικ στον σύνδεσμο: https://t.me/listsongsssbot")
    print("Βήμα 2: Πατήστε 'START' (Έναρξη) ή στείλτε του οποιοδήποτε μήνυμα.")
    print("-" * 65)
    print("⏳ Αναμονή μηνύματος από εσάς στο bot...")

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    
    # We can also handle command line if user passes timeout or loops
    for attempt in range(60):
        try:
            res = requests.get(url, timeout=10).json()
            if res.get("ok"):
                updates = res.get("result", [])
                if updates:
                    last_update = updates[-1]
                    message = last_update.get("message") or last_update.get("channel_post")
                    if message:
                        chat = message.get("chat", {})
                        chat_id = chat.get("id")
                        user_name = chat.get("first_name", "") or chat.get("title", "")
                        
                        print("\n🎉 ΒΡΕΘΗΚΕ!")
                        print(f"👤 Όνομα: {user_name}")
                        print(f"🆔 Chat ID: {chat_id}")
                        
                        # Save to config.json
                        config["telegram_chat_id"] = str(chat_id)
                        with open("config.json", "w", encoding="utf-8") as out:
                            json.dump(config, out, indent=2)
                        print("💾 Το Chat ID αποθηκεύτηκε αυτόματα στο config.json!\n")
                        
                        # Send confirmation message
                        test_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                        requests.post(test_url, json={
                            "chat_id": chat_id,
                            "text": "🎉 <b>Συγχαρητήρια!</b> Το bot σας συνδέθηκε επιτυχώς με την εφαρμογή παρακολούθησης του Spotify!",
                            "parse_mode": "HTML"
                        })
                        print("✉️ Στάλθηκε επιβεβαιωτικό μήνυμα στο Telegram σας!")
                        return
        except Exception as e:
            pass
        time.sleep(2)

    print("\n⚠️ Έληξε ο χρόνος αναμονής. Στείλτε ένα μήνυμα στο @listsongsssbot και ξανατρέξτε το script.")

if __name__ == "__main__":
    main()
