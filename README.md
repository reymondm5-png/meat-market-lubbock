# Meat Market Lubbock — v1.3 automatic weekly-ad discovery

An install-free HTML meat price comparison app plus a **review-first** weekly-ad collector. The collector runs on a GitHub Actions schedule, publishes a same-origin `site/feed.json`, and the app displays suggestions that **must be checked in a real Lubbock store ad** before they're saved. It does not claim unverified third-party offers are local facts.

## Safety / data quality

- Sources: public unofficial Food King weekly-ad product table and a regional United flyer index. The upstream pages may change or block access. HTTP errors, source changes, ambiguous units, or expired ads result in no suggestion.
- Food King ad figures are treated as **shelf prices**, with +10% estimated checkout markup in the app. The actual total may vary with taxes and other discounts.
- For United, the regional listings frequently don't identify `$ / lb`, so item names can appear **without a confirmed per-pound price**.
- `prices` is intentionally an empty array in the automated feed. The app's normal auto-import interface remains available for a separately **verified and permissioned** feed, but this collector never auto-publishes regional price guesses.
- Suggestions expire after their ad end-date. A missed source check does not extrapolate a price.
- No retailer passwords, authentication cookies, hidden API endpoints, or proxy bypasses.
- The collector checks `robots.txt` before requesting a public page; when that check fails, it skips the source.

## Setup

Read `START_HERE.txt` for user-friendly GitHub Desktop + Pages instructions. In short: push the unpacked repo including `.github/workflows/collect.yml`, set GitHub Pages deployment source to **GitHub Actions**, and run the workflow once. The page and feed will publish at `https://USERNAME.github.io/REPOSITORY/` and `.../feed.json` respectively. The app configures that same-origin feed automatically on GitHub Pages.

If using a third-party host instead, configure a scheduled runner and serve `site/` over HTTPS (including `feed.json`) on the same origin as `index.html`.

## Developer tests

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python collector.py --output site/feed.json
```

An unsuccessful or blocked website fetch is recorded in `feed.json.status`, **not** turned into a fabricated price. See `tests/` for offline parser examples.

## The output contract

```json
{
  "location": "Lubbock, TX",
  "asOf": "2026-11-02",
  "prices": [],
  "candidates": [
    {
      "store": "Food King", "meat": "Pork chops",
      "product": "Example cut (NOT a real observed deal)",
      "date": "2026-11-02", "saleEnds": "2026-11-03",
      "pricePerLb": 0.99, "priceIncludesMarkup": false,
      "reviewRequired": true,
      "source": "https://foodking.weeklyad.us.com/"
    }
  ]
}
```

The JSON above is **an illustration of the schema only** and is not embedded in the deployed feed as a claimed price.

### Still on the roadmap

An authorized, store-specific product/weekly-ad feed for United/Food King that provides direct, reliable per-pound pricing. Until one is available this project is intentionally *automatic deal discovery + manual local verification*, not hands-off local pricing.
