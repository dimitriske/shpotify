import re
import json
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from playwright.sync_api import sync_playwright, Playwright, Browser, Page

logger = logging.getLogger("SpotifyScraper")

def parse_spotify_iso_date(iso_str: Optional[str]) -> Tuple[str, float]:
    """
    Μετατρέπει το ISO UTC timestamp του Spotify σε τοπική ημερομηνία/ώρα (YYYY-MM-DD HH:MM:SS)
    και unix timestamp float.
    """
    if not iso_str:
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S"), now.timestamp()
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S"), dt.timestamp()
    except Exception:
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S"), now.timestamp()

class SpotifyScraper:
    """
    Ανακτά τα πλήρη δεδομένα και ΟΛΑ τα τραγούδια (100, 150, 500+)
    οποιασδήποτε δημόσιας λίστας Spotify χωρίς API keys,
    μέσω αυτοματοποιημένης συνεδρίας Playwright και επίσημων Pathfinder queries.
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._auth_header: Optional[str] = None
        self._client_token: Optional[str] = None
        self._last_auth_time: float = 0

    @staticmethod
    def extract_playlist_id(url_or_id: str) -> str:
        url_or_id = url_or_id.strip()
        match = re.search(r"playlist[/:]([a-zA-Z0-9]+)", url_or_id)
        if match:
            return match.group(1)
        if re.match(r"^[a-zA-Z0-9]{15,30}$", url_or_id):
            return url_or_id
        raise ValueError(f"Δεν βρέθηκε έγκυρο ID λίστας: {url_or_id}")

    def _on_request(self, req):
        if "pathfinder" in req.url:
            a = req.headers.get("authorization")
            c = req.headers.get("client-token")
            if a and not self._auth_header:
                self._auth_header = a
            if c and not self._client_token:
                self._client_token = c

    def _ensure_browser(self):
        # Refresh session if older than 1 hour or uninitialized
        now = time.time()
        if (
            self._browser is not None
            and self._page is not None
            and self._auth_header
            and (now - self._last_auth_time < 3600)
        ):
            return

        self._close_browser()
        logger.info("Εκκίνηση ασφαλούς συνεδρίας Spotify Web...")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        self._page = self._browser.new_page()
        self._page.on("request", self._on_request)

        # Navigate to spotify web to acquire valid authorization & client-token
        self._auth_header = None
        self._client_token = None
        try:
            self._page.goto("https://open.spotify.com", timeout=self.timeout * 1000)
            self._page.wait_for_timeout(3500)
        except Exception as e:
            logger.warning(f"Προειδοποίηση κατά τη φόρτωση του Spotify: {e}")

        if not self._auth_header:
            # Fallback: wait a bit more if token not yet acquired
            self._page.wait_for_timeout(2000)

        self._last_auth_time = time.time()
        logger.info(f"Συνεδρία Spotify Web έτοιμη (Auth: {bool(self._auth_header)}, Token: {bool(self._client_token)})")

    def _close_browser(self):
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._browser = None
        self._pw = None

    def fetch_playlists_batch(self, urls_or_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Ανακτά ταυτόχρονα όλες τις λίστες της λίστας urls_or_ids με πλήρη σελιδοποίηση (>100 τραγούδια).
        Εξαιρετικά γρήγορο (~3-4 δευτερόλεπτα για 27 λίστες).
        """
        self._ensure_browser()

        pids = []
        for item in urls_or_ids:
            try:
                pids.append(self.extract_playlist_id(item))
            except Exception:
                pass

        if not pids:
            return []

        js_fetch = """
        async (args) => {
            const { pids, headers } = args;
            const sha256 = '21ea11a6ac75a5f3e01fd365d29c18e0a4a8b7dc09f89bbb5d73910190c6acaf';
            
            async function fetchSingle(pid) {
                let allItems = [];
                let offset = 0;
                let playlistName = '';
                let author = '';
                while (true) {
                    const res = await fetch('https://api-partner.spotify.com/pathfinder/v2/query', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': headers.auth,
                            ...(headers.clientToken ? {'Client-Token': headers.clientToken} : {})
                        },
                        body: JSON.stringify({
                            operationName: 'fetchPlaylist',
                            variables: {
                                uri: 'spotify:playlist:' + pid,
                                offset: offset,
                                limit: 100,
                                enableWatchFeedEntrypoint: false,
                                includeEpisodeContentRatingsV2: true
                            },
                            extensions: {
                                persistedQuery: {
                                    version: 1,
                                    sha256Hash: sha256
                                }
                            }
                        })
                    });
                    if (!res.ok) break;
                    const data = await res.json();
                    const pl = data?.data?.playlistV2;
                    if (!pl) break;
                    playlistName = pl.name || playlistName;
                    author = pl.ownerV2?.data?.name || author;
                    const items = pl.content?.items || [];
                    if (items.length === 0) break;
                    allItems.push(...items);
                    if (items.length < 100) break;
                    offset += 100;
                }
                return {
                    id: pid,
                    title: playlistName,
                    author: author,
                    total_tracks: allItems.length,
                    raw_items: allItems.map(it => ({
                        id: (it.itemV2?.data?.uri || '').split(':').pop(),
                        title: it.itemV2?.data?.name || 'Χωρίς τίτλο',
                        artist: (it.itemV2?.data?.artists?.items || []).map(a => a.profile?.name).filter(Boolean).join(', ') || 'Άγνωστος',
                        added_at_iso: it.addedAt?.isoString || ''
                    }))
                };
            }
            
            const results = [];
            for (let i = 0; i < pids.length; i += 6) {
                const chunk = pids.slice(i, i + 6);
                const chunkRes = await Promise.all(chunk.map(pid => fetchSingle(pid)));
                results.push(...chunkRes);
            }
            return results;
        }
        """

        try:
            raw_results = self._page.evaluate(
                js_fetch,
                {
                    "pids": pids,
                    "headers": {
                        "auth": self._auth_header,
                        "clientToken": self._client_token,
                    }
                }
            )
        except Exception as e:
            logger.warning(f"Σφάλμα κατά την εκτέλεση evaluation, επαναφορά συνεδρίας: {e}")
            self._close_browser()
            self._ensure_browser()
            raw_results = self._page.evaluate(
                js_fetch,
                {
                    "pids": pids,
                    "headers": {
                        "auth": self._auth_header,
                        "clientToken": self._client_token,
                    }
                }
            )

        parsed_playlists: List[Dict[str, Any]] = []
        for r in raw_results:
            pid = r.get("id", "")
            title = r.get("title") or f"Λίστα {pid}"
            author = r.get("author") or "Δημιουργός"

            tracks = []
            for item in r.get("raw_items", []):
                tid = item.get("id", "")
                iso_str = item.get("added_at_iso", "")
                dt_str, ts = parse_spotify_iso_date(iso_str)

                tracks.append({
                    "id": tid,
                    "title": item.get("title", "Χωρίς τίτλο"),
                    "artist": item.get("artist", "Άγνωστος"),
                    "url": f"https://open.spotify.com/track/{tid}" if tid else "",
                    "added_at": dt_str,
                    "added_timestamp": ts,
                })

            parsed_playlists.append({
                "id": pid,
                "title": title,
                "author": author,
                "url": f"https://open.spotify.com/playlist/{pid}",
                "total_tracks": len(tracks),
                "tracks": tracks,
            })

        return parsed_playlists

    def fetch_playlist_data(self, playlist_url_or_id: str) -> Dict[str, Any]:
        """
        Ανακτά τα πλήρη δεδομένα μιας μεμονωμένης λίστας.
        """
        res = self.fetch_playlists_batch([playlist_url_or_id])
        if res:
            return res[0]
        raise RuntimeError(f"Αποτυχία ανάκτησης λίστας: {playlist_url_or_id}")

    def close(self):
        self._close_browser()
