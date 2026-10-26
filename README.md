# 🎵 Spotify Multi-Playlist Monitor & Telegram Alerts (No-API)

Μια αυτόνομη Python εφαρμογή που παρακολουθεί ταυτόχρονα **όλες τις δημόσιες λίστες** ενός χρήστη ή πολλές λίστες αναπαραγωγής στο Spotify **χωρίς τη χρήση του επίσημου Spotify API** (χωρίς client_id / secret / developer credentials).

---

## ⚡ Χαρακτηριστικά

* 🎧 **Παρακολούθηση πολλαπλών λιστών ταυτόχρονα**: Ελέγχει και τις 27 λίστες σε μόλις 3-4 δευτερόλεπτα με παράλληλα threads (ThreadPoolExecutor).
* 📁 **Ενιαίο Αρχείο Κατάστασης (`playlist_state.json`)**: Όλες οι λίστες και τα τραγούδια τους είναι αποθηκευμένα τοπικά σε ένα αρχείο.
* 🤖 **Άμεσες Ειδοποιήσεις στο Telegram**:
  * 🟢 **Προσθήκη νέου τραγουδιού**: Εμφανίζει το όνομα της λίστας, τον τίτλο, τον καλλιτέχνη και σύνδεσμο στο Spotify.
  * 🔴 **Αφαίρεση τραγουδιού**: Εμφανίζει ποιο τραγούδι αφαιρέθηκε και από ποια λίστα.
* 🔄 **Αυτόματη Αποθήκευση**: Μόλις εντοπιστεί αλλαγή, ενημερώνει αμέσως το τοπικό αρχείο ώστε να μη στέλνει διπλές ειδοποιήσεις.
* 🚀 **Αυτόματος Συγχρονισμός Προφίλ (`--sync-user`)**: Μπορεί να αντλήσει αυτόματα όλες τις δημόσιες λίστες από το προφίλ ενός χρήστη.

---

## ⚙️ Ρυθμίσεις (`config.json`)

```json
{
  "spotify_user_url": "https://open.spotify.com/user/315fle6y4n6ezwdxbjhnsuc7gk6q/playlists",
  "spotify_playlists": [
    "https://open.spotify.com/playlist/5gts5yEzRY9HrljsuEic9s",
    "https://open.spotify.com/playlist/5cYAK5XTVTPvMiOTkqDvxS",
    "https://open.spotify.com/playlist/12gExXaqFh9fshhTcFqzYH",
    "... όλες οι υπόλοιπες λίστες ..."
  ],
  "telegram_bot_token": "8332255079:AAEJ1Xus8fI4kB6u8G9ClCf4guuT-ynIknk",
  "telegram_chat_id": "1472813115",
  "check_interval_seconds": 60,
  "notify_on_start": true
}
```

---

## ▶️ Εκτέλεση

### 1. Συνεχής παρακολούθηση (Monitor Loop):
Κάντε διπλό κλικ στο:
📁 **[start.bat](file:///c:/Users/dimit/Desktop/list%20song/start.bat)** (ή τρέξτε `python main.py` στο τερματικό).

### 2. Ένας μεμονωμένος έλεγχος όλων των λιστών:
```powershell
python main.py --check-once
```

### 3. Αυτόματος συγχρονισμός αν προστεθούν νέες λίστες στο προφίλ:
```powershell
python main.py --sync-user https://open.spotify.com/user/315fle6y4n6ezwdxbjhnsuc7gk6q/playlists
```
