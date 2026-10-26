# Researching a card data source

Look in this order, and keep going until there are at least two candidates or you have run out of places.

1. **The publisher.** An official API, data export, or downloadable card list; the "card gallery" pages are usually a last resort. Official sources have the best licence position and the most stable image URLs.
2. **Community databases and APIs.** For example a fan-run card DB with a JSON API. Check who maintains it and when it last updated.
3. **GitHub JSON repositories.** Search for `<game> cards json` and look at stars, recent commits and a LICENSE. A tarball of a commit is the easiest thing to fetch and gives a natural `source_ref` (the SHA).
4. **Wikis and scraping.** Last. They need parsing, break when the markup changes, and may forbid it.

Use light requests only (a single API call, `HEAD` on an image, the repository page). Do not download a whole dataset until the user has chosen.

## What to report for each candidate

| Question | What to find out |
| --- | --- |
| Format | JSON, CSV, XML, an HTML page; one file or many |
| Coverage | all sets or some; languages; errata and reprints; tokens and non-card items |
| Update cadence | last update, how new sets arrive, whether old data is corrected in place |
| Stable id | a field that is unique per card and never changes (not the name, not an array position) |
| Images | who hosts them, the URL pattern, whether URLs are permanent, whether hotlinking is allowed |
| Licence and terms | the data licence, the site's terms of use, any fan-content policy, attribution required |
| Fetch method | one request, a paginated API (rate limit, key needed?), a tarball, a scrape; and a cheap way to get the current version (`latest_ref`) |

## Judging them

- A stable id and clear terms decide more than coverage: coverage can be patched, a changing id cannot.
- Prefer a source that is versioned (commit SHA, ETag, API version) so updates can be detected without downloading.
- Image URLs from the publisher or a long-lived CDN beat a community host; note any that need a key.
- Say plainly if a source needs an API key, an account or a scrape of a site whose terms forbid it.

## Presenting the choice

Give a table with one row per candidate and the questions above as columns, then a recommendation with the reason in a sentence or two, and the risk if it is chosen (for example "single maintainer, last commit 8 months ago"). Ask the user to choose.
