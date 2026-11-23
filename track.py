"""Track every open HiBid lot for the searches in searches.txt.

Runs once and exits (GitHub Actions calls it every 15 minutes). Writes data.json,
which the dashboard (docs/index.html) groups into price ranges.
Run locally: python track.py
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---- settings -------------------------------------------------------------

SEARCHES_FILE = Path(__file__).parent / "searches.txt"
DATA_FILE = Path(__file__).parent / "data.json"
TITLE_MUST_MATCH = True    # keep a lot only if every search word is in its title (HiBid also matches descriptions)
MAX_LOTS_PER_SEARCH = 1000  # safety cap
PAGE_SIZE = 100

# ---------------------------------------------------------------------------

QUERY = """
query Q($q: String, $auctionId: Int, $page: Int!, $size: Int!) {
  lotSearch(input: {searchText: $q, auctionId: $auctionId, status: OPEN, countAsView: false},
            pageNumber: $page, pageLength: $size, sortDirection: DESC) {
    pagedResults {
      totalCount
      results {
        id lead lotNumber
        featuredPicture { thumbnailLocation }
        auction { id eventName bidCloseDateTime currencyAbbreviation auctioneer { name } }
        lotState { highBid minBid bidCount isClosed }
      }
    }
  }
}
"""

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def read_searches():
    out = []
    for line in SEARCHES_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in out:
            out.append(line)
    return out


def parse_search(url):
    """https://encoreauctions.hibid.com/lots?q=desk  (also /catalog/<auctionId>/...?q=desk)"""
    u = urllib.parse.urlparse(url)
    if not u.hostname or not u.hostname.endswith("hibid.com"):
        raise ValueError("not a HiBid URL (expected https://<site>.hibid.com/lots?q=desk)")
    qs = urllib.parse.parse_qs(u.query)
    q = (qs.get("q") or qs.get("searchText") or [""])[0].strip()
    if not q:
        raise ValueError("no search words in the URL (expected ...?q=desk)")
    m = re.search(r"/catalog/(\d+)", u.path)
    return u.hostname, q, int(m.group(1)) if m else None


def gql(host, variables):
    req = urllib.request.Request(
        f"https://{host}/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA,
                 "Origin": f"https://{host}", "Referer": f"https://{host}/lots"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.load(r)
            if data.get("errors"):
                raise RuntimeError(str(data["errors"])[:300])
            return data["data"]["lotSearch"]["pagedResults"]
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def run_search(url):
    host, q, auction_id = parse_search(url)
    words = [w for w in re.findall(r"\w+", q.lower())]
    lots, page = [], 1
    while len(lots) < MAX_LOTS_PER_SEARCH:
        res = gql(host, {"q": q, "auctionId": auction_id, "page": page, "size": PAGE_SIZE})
        batch = res["results"] or []
        for r in batch:
            title = r["lead"] or ""
            if TITLE_MUST_MATCH and not all(re.search(rf"\b{re.escape(w)}", title.lower()) for w in words):
                continue
            s, a = r["lotState"], r.get("auction") or {}
            if s.get("isClosed"):
                continue
            lots.append({
                "id": str(r["id"]),
                "title": title,
                "lot_number": r.get("lotNumber") or "",
                "url": f"https://{host}/lot/{r['id']}/{slug(title)}",
                "image": (r.get("featuredPicture") or {}).get("thumbnailLocation") or "",
                "auction": a.get("eventName") or "",
                "auctioneer": (a.get("auctioneer") or {}).get("name") or "",
                "closes": a.get("bidCloseDateTime") or "",
                "currency": a.get("currencyAbbreviation") or "",
                "high": s.get("highBid") or 0,
                "price": s.get("minBid") or 0,   # what you'd have to bid now
                "bids": s.get("bidCount") or 0,
            })
        if len(batch) < PAGE_SIZE or page * PAGE_SIZE >= res["totalCount"]:
            break
        page += 1
    lots = list({l["id"]: l for l in lots}.values())  # HiBid's paging order isn't stable: dedupe and
    lots.sort(key=lambda l: int(l["id"]))              # sort so unchanged results don't cause a commit
    return {"query": q, "host": host, "url": url, "lots": lots}


def main():
    old = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}
    seen_before = {l["id"]: l.get("first_seen") for s in old.get("searches", []) for l in s.get("lots", [])}
    old_by_url = {s["url"]: s for s in old.get("searches", [])}
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    searches, failures = [], 0
    for url in read_searches():
        try:
            s = run_search(url)
            for l in s["lots"]:
                l["first_seen"] = seen_before.get(l["id"]) or stamp
            s["added"] = (old_by_url.get(url) or {}).get("added") or stamp  # lots seen on the first run aren't "new"
            s["error"] = ""
            print(f"{s['query']!r} @ {s['host']}: {len(s['lots'])} open lots")
        except Exception as e:  # keep the last good results, show the error on the dashboard
            failures += 1
            print(f"ERROR {url}: {e}", file=sys.stderr)
            s = dict(old_by_url.get(url) or {"url": url, "query": url, "lots": []})
            s["error"] = str(e)[:200]
        searches.append(s)

    new = {"searches": searches}
    if json.dumps(new, sort_keys=True) != json.dumps({"searches": old.get("searches", [])}, sort_keys=True):
        new["updated"] = stamp
        DATA_FILE.write_text(json.dumps(new, indent=1) + "\n")
        print("data.json updated")
    if searches and failures == len(searches):
        sys.exit(1)


if __name__ == "__main__":
    main()
