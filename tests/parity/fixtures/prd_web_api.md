# PRD: URL-shortener API

## Goal
Build a small HTTP service that shortens URLs and redirects short codes.

## Requirements
- `POST /shorten` accepts a JSON `{ "url": "..." }` and returns a short code.
- `GET /<code>` issues a 301 redirect to the original URL.
- Duplicate URLs return the existing code instead of minting a new one.
- Invalid or missing URLs return a 400 with a JSON error body.
- Codes persist across restarts in a SQLite store.

## Acceptance
- A shortened URL round-trips: shorten then follow the code reaches the origin.
- Unknown codes return 404.
