# Tests

Detection accuracy is the whole product. Tests run the detectors against saved fixtures (real HTML snippets and real email bodies) and assert the detected position is correct.

## Fixtures

- `fixtures/web/` — saved HTML snippets from real sites. Each file pairs `.html` (the page) with `.expected.txt` (the first 200 characters of where detection SHOULD land). Aim for a spread: news articles, blog posts, app dashboards, form-primary pages, sites with heavy cookie banners and ads.
- `fixtures/email/` — saved message bodies as plain text. Pairs `.eml.txt` with `.expected.txt`. Include a spread: top-posted Outlook reply, bottom-posted with `-- ` delimiter, multi-quote chain, "From: ... Sent: ..." block headers, no quoted content, signature with org keywords, signature without.

## Approach

Once detectors are implemented, write a small pytest driver that:

1. Loads each fixture pair.
2. Calls the relevant detector.
3. Compares the leading N characters of detected content against `expected.txt`.
4. Reports pass/fail per fixture, summary at end.

Run from project root:

```
pytest tests/
```

## Why fixtures and not live sites

Live sites change. Tests must be deterministic. Save the HTML/body once, assert against it. When a site changes its layout, update the fixture intentionally.

## Adding a fixture for a misdetection

When a user reports "it picked the wrong spot on news.example.com," save the HTML as a new fixture, write the expected content-start to a paired file, and watch the test fail. Fix the heuristic until the test passes. Existing fixtures must still pass — that's the regression guard.
