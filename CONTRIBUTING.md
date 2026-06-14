# Contributing

Thanks for helping curate this list! A few quick guidelines:

## Adding a blog

1. Make sure the blog has a working **RSS / Atom feed**. No feed → it can't be aggregated.
2. The blog should publish **substantive ML / AI content** — research notes, engineering deep-dives,
   model cards, applied case studies. Marketing-only blogs will be rejected.
3. Add the blog in **alphabetical order** within its category in `README.md`.
4. Add the same blog to `ai_engineering_blogs.opml` so RSS aggregators pick it up.
5. Prefer the canonical feed URL (e.g. `https://example.com/feed.xml`) over a third-party mirror.

## Format

In `README.md`:

```markdown
- [Blog Name](https://blog.example.com/) — one-line description ([RSS](https://blog.example.com/feed.xml))
```

In `ai_engineering_blogs.opml`:

```xml
<outline type="rss" text="Blog Name" title="Blog Name"
         xmlUrl="https://blog.example.com/feed.xml"
         htmlUrl="https://blog.example.com/" />
```

## Pull requests

- One blog per PR keeps review easy; bulk additions are fine if you've checked every feed.
- Verify the feed actually loads (e.g. `curl -I <feed-url>`) before opening the PR.
- Dead feeds get removed. If you spot one, a PR removing it is just as welcome as adding a new one.