# Auction Deals

Tracks every open lot for your HiBid searches (e.g. "desk") and shows them grouped by price:
under 10, 10-20, 20-50, 50-100, 100+. Runs free on GitHub Actions every ~15 minutes.

**Dashboard:** https://harshil3134.github.io/auction-deals/

## Add a search
1. Search on the auction site (e.g. https://encoreauctions.hibid.com), copy the address bar:
   `https://encoreauctions.hibid.com/lots?q=desk`
2. Dashboard -> **Add / remove searches** (opens `searches.txt` in GitHub's editor), paste it on a new line, Commit.
   Saving the file starts a check right away.

A search on an auctioneer's own site (`encoreauctions.hibid.com`) only covers that auctioneer;
`hibid.com/lots?q=desk` searches every auctioneer (thousands of lots, capped at 1000 per search).

## How it works
- `track.py` calls HiBid's public GraphQL search (`lotSearch`, status OPEN) for each URL in `searches.txt`
  and writes `data.json`. Lots need every search word in the title (`TITLE_MUST_MATCH`).
- "Price" is HiBid's minimum next bid: what you'd pay to bid now. Groups are set by `RANGES` in `docs/index.html`.
- `docs/index.html` (GitHub Pages) reads `data.json` from the repo. NEW = appeared in the last 24 h
  (not counting a search's first run).

## Run locally
`python3 track.py` (no dependencies). Repo must stay public for unlimited free Actions minutes.
