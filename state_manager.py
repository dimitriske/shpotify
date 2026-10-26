import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional

class StateManager:
    """
    Διαχειρίζεται την τοπική αποθήκευση των τραγουδιών (playlist_state.json),
    το ιστορικό προσθηκών/αφαιρέσεων και την ημερομηνία/ώρα κάθε τραγουδιού.
    """

    def __init__(self, state_file: str = "playlist_state.json"):
        self.state_file = state_file

    def _load_all(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_file):
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_all(self, data: Dict[str, Any]) -> None:
        temp_file = f"{self.state_file}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, self.state_file)

    def load_playlist_state(self, playlist_id: str) -> Optional[Dict[str, Any]]:
        all_states = self._load_all()
        return all_states.get(playlist_id)

    def save_playlist_state(
        self,
        playlist_data: Dict[str, Any],
        added_tracks: Optional[List[Dict[str, Any]]] = None,
        removed_tracks: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        all_states = self._load_all()
        playlist_id = playlist_data["id"]
        playlist_title = playlist_data["title"]
        now_ts = time.time()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        existing = all_states.get(playlist_id, {})
        existing_tracks_map = {t["id"]: t for t in existing.get("tracks", []) if t.get("id")}

        processed_tracks: List[Dict[str, Any]] = []
        for t in playlist_data["tracks"]:
            tid = t.get("id")
            if tid in existing_tracks_map and "added_at" in existing_tracks_map[tid]:
                track_added_at = existing_tracks_map[tid]["added_at"]
                track_added_ts = existing_tracks_map[tid].get("added_timestamp", now_ts)
            elif t.get("added_at"):
                track_added_at = t["added_at"]
                track_added_ts = t.get("added_timestamp", now_ts)
            else:
                track_added_at = now_str
                track_added_ts = now_ts

            processed_tracks.append({
                "id": tid,
                "title": t.get("title", "Χωρίς τίτλο"),
                "artist": t.get("artist", "Άγνωστος"),
                "url": t.get("url", f"https://open.spotify.com/track/{tid}" if tid else ""),
                "added_at": track_added_at,
                "added_timestamp": track_added_ts,
            })

        all_states[playlist_id] = {
            "playlist_id": playlist_id,
            "playlist_title": playlist_title,
            "playlist_author": playlist_data.get("author", "Δημιουργός"),
            "last_updated": now_ts,
            "total_tracks": len(processed_tracks),
            "tracks": processed_tracks,
        }

        # History log
        history = all_states.get("_history", [])
        if added_tracks:
            for at in added_tracks:
                history.append({
                    "action": "added",
                    "playlist_id": playlist_id,
                    "playlist_title": playlist_title,
                    "track_title": at.get("title", "Χωρίς τίτλο"),
                    "track_artist": at.get("artist", "Άγνωστος"),
                    "url": at.get("url", ""),
                    "datetime": at.get("added_at", now_str),
                    "timestamp": at.get("added_timestamp", now_ts),
                })

        if removed_tracks:
            for rt in removed_tracks:
                history.append({
                    "action": "removed",
                    "playlist_id": playlist_id,
                    "playlist_title": playlist_title,
                    "track_title": rt.get("title", "Χωρίς τίτλο"),
                    "track_artist": rt.get("artist", "Άγνωστος"),
                    "datetime": now_str,
                    "timestamp": now_ts,
                })

        # Keep last 1000 history events
        if len(history) > 1000:
            history = history[-1000:]
        all_states["_history"] = history

        self._save_all(all_states)

    def diff_tracks(
        self, old_tracks: List[Dict[str, Any]], new_tracks: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        old_ids = {t["id"]: t for t in old_tracks if t.get("id")}
        new_ids = {t["id"]: t for t in new_tracks if t.get("id")}

        added = [track for track_id, track in new_ids.items() if track_id not in old_ids]
        removed = [track for track_id, track in old_ids.items() if track_id not in new_ids]

        return added, removed

    def get_all_playlists_summary(self) -> List[Dict[str, Any]]:
        all_states = self._load_all()
        summary = []
        for pid, pdata in all_states.items():
            if pid.startswith("_"):
                continue
            summary.append({
                "id": pid,
                "title": pdata.get("playlist_title", pid),
                "author": pdata.get("playlist_author", "Δημιουργός"),
                "total_tracks": pdata.get("total_tracks", len(pdata.get("tracks", []))),
                "tracks": pdata.get("tracks", []),
            })
        summary.sort(key=lambda x: x["title"].lower())
        return summary

    def get_changes_today(self, playlist_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Επιστρέφει τα τραγούδια που προστέθηκαν σήμερα (από 00:00).
        Ελέγχει τόσο το ιστορικό αλλαγών όσο και τις ημερομηνίες προσθήκης των τραγουδιών.
        """
        all_states = self._load_all()
        now = datetime.now()
        start_of_today = datetime(now.year, now.month, now.day).timestamp()
        today_date_prefix = now.strftime("%Y-%m-%d")

        grouped: Dict[str, Dict[str, Any]] = {}

        def get_grp(pid, title):
            if pid not in grouped:
                grouped[pid] = {
                    "playlist_id": pid,
                    "playlist_title": title,
                    "added": [],
                    "removed": []
                }
            return grouped[pid]

        # 1. Check history
        history = all_states.get("_history", [])
        for h in history:
            if playlist_id and h.get("playlist_id") != playlist_id:
                continue
            ts = h.get("timestamp", 0)
            dt_str = h.get("datetime", "")
            if ts >= start_of_today or dt_str.startswith(today_date_prefix):
                grp = get_grp(h["playlist_id"], h.get("playlist_title", "Λίστα"))
                if h.get("action") == "added":
                    if not any(x.get("track_title") == h.get("track_title") for x in grp["added"]):
                        grp["added"].append(h)
                elif h.get("action") == "removed":
                    if not any(x.get("track_title") == h.get("track_title") for x in grp["removed"]):
                        grp["removed"].append(h)

        # 2. Check playlist tracks directly
        for pid, pdata in all_states.items():
            if pid.startswith("_"):
                continue
            if playlist_id and pid != playlist_id:
                continue
            title = pdata.get("playlist_title", pid)
            for t in pdata.get("tracks", []):
                t_ts = t.get("added_timestamp", 0)
                t_dt = t.get("added_at", "")
                if t_ts >= start_of_today or t_dt.startswith(today_date_prefix):
                    grp = get_grp(pid, title)
                    if not any(x.get("track_title") == t.get("title") for x in grp["added"]):
                        grp["added"].append({
                            "action": "added",
                            "playlist_id": pid,
                            "playlist_title": title,
                            "track_title": t.get("title", "Χωρίς τίτλο"),
                            "track_artist": t.get("artist", "Άγνωστος"),
                            "url": t.get("url", ""),
                            "datetime": t_dt,
                            "timestamp": t_ts,
                        })

        return {k: v for k, v in grouped.items() if v["added"]}

    def get_changes_week(self, playlist_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Επιστρέφει τα τραγούδια που προστέθηκαν τις τελευταίες 7 ημέρες.
        """
        all_states = self._load_all()
        one_week_ago = (datetime.now() - timedelta(days=7)).timestamp()

        grouped: Dict[str, Dict[str, Any]] = {}

        def get_grp(pid, title):
            if pid not in grouped:
                grouped[pid] = {
                    "playlist_id": pid,
                    "playlist_title": title,
                    "added": [],
                    "removed": []
                }
            return grouped[pid]

        history = all_states.get("_history", [])
        for h in history:
            if playlist_id and h.get("playlist_id") != playlist_id:
                continue
            ts = h.get("timestamp", 0)
            if ts >= one_week_ago:
                grp = get_grp(h["playlist_id"], h.get("playlist_title", "Λίστα"))
                if h.get("action") == "added":
                    if not any(x.get("track_title") == h.get("track_title") for x in grp["added"]):
                        grp["added"].append(h)
                elif h.get("action") == "removed":
                    if not any(x.get("track_title") == h.get("track_title") for x in grp["removed"]):
                        grp["removed"].append(h)

        for pid, pdata in all_states.items():
            if pid.startswith("_"):
                continue
            if playlist_id and pid != playlist_id:
                continue
            title = pdata.get("playlist_title", pid)
            for t in pdata.get("tracks", []):
                t_ts = t.get("added_timestamp", 0)
                if t_ts >= one_week_ago:
                    grp = get_grp(pid, title)
                    if not any(x.get("track_title") == t.get("title") for x in grp["added"]):
                        grp["added"].append({
                            "action": "added",
                            "playlist_id": pid,
                            "playlist_title": title,
                            "track_title": t.get("title", "Χωρίς τίτλο"),
                            "track_artist": t.get("artist", "Άγνωστος"),
                            "url": t.get("url", ""),
                            "datetime": t.get("added_at", ""),
                            "timestamp": t_ts,
                        })

        return {k: v for k, v in grouped.items() if v["added"]}
