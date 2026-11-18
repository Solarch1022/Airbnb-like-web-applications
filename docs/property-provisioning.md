# Property provisioning and booking mode — Phase 2 / Notion 04 and 04a

Issue: https://github.com/Solarch1022/Airbnb-like-web-applications/issues/15
04: https://app.notion.com/p/3c38a059477280c19050c2d893201861
04a: https://app.notion.com/p/3f48a059477280c4a551c3a91ae0d206

## Product baseline for manual review

- Keep the simple Phase 1 permissions: active organisation admins configure, publish, take offline and archive. Active members read management data/readiness. Anonymous customers read only ACTIVE, ready listings belonging to ACTIVE organisations.
- No implicit booking-mode default. A draft may omit mode; publication requires explicit INSTANT or REQUEST. Changing mode or price affects new bookings only. The later booking implementation must snapshot mode, price/currency, stay dates and applicable rules when creating a booking. Existing CONFIRMED/PENDING bookings retain their original state/approval flow; changing a listing never auto-confirms, cancels or reprices them. No booking records are rewritten here.
- MVP publication currencies: AUD, USD, EUR, GBP, NZD. Nightly prices retain two decimal places. Other three-letter codes can be saved in a draft but are rejected by readiness until supported. This bounded currency list is an implementation choice for review, not a supervisor-approved requirement.
- Stay limits: explicit min_nights and max_nights, each integer 1–90, max >= min. Preparation gap: explicit preparation_nights integer 0–7. Zero is valid and does not mean missing. These bounds are MVP choices for review. Drafts may omit rules and save progress.
- blocked_dates is a sorted, unique list of calendar dates, maximum 366 entries. Empty means no manual blocks. Dates represent calendar days, not timestamps. Date-based availability/occupancy and timezone policy are implemented in task 05. Stays will use [check_in, check_out); publication alone does not guarantee any date is available.
- public_location is a city/area label. The management address remains private and is excluded from public schemas. Description/title are deliberately public listing content.
- Image handling remains URL references (HTTP/HTTPS, up to 20); publication requires at least one syntactically valid reference. This increment does not upload, fetch, or verify remote image content. Use a working URL in the manual test. The public page displays a fallback if an image fails. Saved drafts remain intact on validation failures.
- No separate publication approver. The organisation admin publishes after readiness passes. No invitations, payments, temporary locks, booking approval or date allocation are added here.

## Lifecycle

```text
DRAFT --ready + Publish--> ACTIVE --Take offline--> INACTIVE
                               ^                       |
                               +--ready + Publish------+
DRAFT / ACTIVE / INACTIVE --Archive--> ARCHIVED
```

- Edit DRAFT/INACTIVE incrementally. ACTIVE edits must remain publishable; missing mode/images or unsupported currency returns 422 without changing the listing. Take offline first if setup needs to become incomplete.
- ARCHIVED is read-only and cannot be republished. DRAFT and eligible never-published archived drafts retain Delete draft. Any property ever published retains published_at permanently and cannot be permanently deleted, including after taking offline/archive.
- First successful publish sets published_at; later publication preserves it. Every actual mutation increments version. All writes atomically recheck account/org/admin membership, expected version and source status.
- Repeated Publish on ACTIVE or Take offline on INACTIVE with the current version returns the same record. A stale version returns 409, including retrying the version used before a successful transition. Reload/review rather than silently applying to changed data.
- When has_booking_history is true, changing blocked_dates or preparation_nights returns 409 until booking conflict checks exist. The UI disables these calendar fields. This prevents unconditional overwrites of future booked dates. Later booking transactions must set has_booking_history and increment/check property version atomically with allocations. Published_at/history markers must never be cleared.

## Management API

Base: `/organisations/{organisation_id}/properties/{property_id}`

| Method | Path | Access | Response |
|---|---|---|---|
| GET | base/readiness | Member/admin | ready, can_publish, version, status, issues[{field,message}] |
| POST | base/publish | Admin | ACTIVE property |
| POST | base/deactivate | Admin | INACTIVE property |
| PATCH | base | Admin | Updated DRAFT/ACTIVE/INACTIVE; original partial-update/version semantics |
| DELETE | base?expected_version=... | Admin | Archive from any unarchived lifecycle state |

Publish/deactivate body: `{"expected_version": 2}`. Extra fields, booleans and missing versions are rejected. Publishing reruns readiness on the current property; a prior successful readiness GET does not bypass the write/version checks.

New editable setup fields:

```json
{
  "public_location": "Perth, WA",
  "min_nights": 1,
  "max_nights": 14,
  "preparation_nights": 0,
  "blocked_dates": ["2026-12-24", "2026-12-25"]
}
```

PATCH must additionally include expected_version. Null may clear optional setup fields on an unpublished/offline property; blocked_dates must use [] instead of null. A partial min/max patch is validated against the retained opposite limit.

Readiness requires title, description, private address, public location, type, positive price, supported currency, capacity, at least one image URL, explicit mode, min/max stay and preparation nights. It returns all missing items. Configuration readiness is independent of lifecycle: an archive may have complete fields, but can_publish remains false.

Errors preserve the 03 policy: 401 identity, 403 organisation/role or revoked write permission, 404 inaccessible property, 409 stale version/lifecycle/calendar constraints, 422 input/readiness. Operational DB failures propagate. Draft delete still returns 204 and original creation retries after deletion return 410.

## Public discovery

- Page: `/listings?organisation_id=<id>`; management provides View public listings.
- GET `/public/organisations/{organisation_id}/properties?limit=20&cursor=...`.
- GET `/public/organisations/{organisation_id}/properties/{property_id}`.
- No mandatory authentication. Missing/inactive organisation or hidden/missing detail returns 404. Draft/inactive/archived records never appear. Public visibility is re-evaluated on each API request; refresh an already-open page after a lifecycle change.
- Public fields: property_id, title, description, public_location, property_type, price_per_night, currency, max_guests, images, booking_mode, min_nights, max_nights. Never expose exact address, account/creator metadata, membership, version, lifecycle/history flags or blocked/preparation dates.
- Discovery is organisation-scoped; no global table Scan or new index is needed. Filtering uses the existing paginated Query. A filtered page can be empty with a next_cursor; the page keeps Load more so callers can reach later published records.
- No availability or Book button yet. Public status/mode describes the configured listing, not a completed booking workflow.

## Compatibility and persistence

No table migrations or new tables. New fields default to incomplete setup on old 03 rows; old records are not auto-published. Decimal-to-int restoration includes min/max/preparation counts. Dates/URL references persist using JSON-safe values. Existing created_at, created_by, immutable scope, deletion markers and idempotency audit records remain intact.

Creation replays support the original 03 fingerprint when all new setup fields are unset; supplying new configuration with the old key correctly returns 409. Fresh creations hash the full normalised payload. A caller intentionally creating another draft needs a new key.

## Automated tests

```bash
.venv/bin/python -m pytest tests/test_property_provisioning.py -v
docker compose up -d dynamodb-local
.venv/bin/python -m pytest tests/integration/test_provisioning_integration.py -v
.venv/bin/python -m pytest tests -v
git diff --check
```

Integration fixtures only create/delete randomly named test tables. Tests cover both modes, integer/date serialisation, lifecycle and privacy, access-revocation rollback, publication competing with edit/delete/publication, and legacy setup defaults. Skipped integration tests do not count as database verification.

## Manual review

1. Restart the API to load the new routes/models:

   ```bash
   DYNAMODB_ENDPOINT_URL=http://localhost:8000 AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AUTO_CREATE_TABLE=true .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
   ```

2. Open `/management`, sign in with the existing phase2.admin@example.com local account, choose Phase 2 Test Organisation. Existing records remain in place. Create a new draft named "Phase 2 Provisioning Test" using a title only. Check readiness: missing items appear and Publish must not change status.
3. Edit and save with description, private address, public location "Perth, WA", type "Apartment", AUD 120.50, capacity 2, min nights 1, max nights 14, preparation 0, optional blocked dates, and one working HTTP/HTTPS image URL. First leave mode unset: readiness must still show booking_mode missing. Choose REQUEST explicitly and save.
4. Check readiness, Publish and confirm: ACTIVE, version increments, Delete draft disappears, Take offline and Archive remain. View public listings: the listing appears anonymously, shows REQUEST and public location, and does not expose exact address or private metadata.
5. Edit ACTIVE mode to INSTANT and price to 150.00. Save and refresh public listings: values update. Clearing mode/images on ACTIVE must fail without losing saved state. Future booking snapshots are a documented contract; no actual bookings exist in this increment.
6. Take offline: INACTIVE and hidden from public discovery/detail. Save incomplete setup while offline: republish must fail until missing items are restored. Republish, then Archive: public entry disappears, first publication timestamp remains, permanent deletion is unavailable. Create a separate draft to test Delete draft.
7. Sign in as phase2.member@example.com: view/readiness allowed, edits and lifecycle buttons absent. API writes must return 403. Expired/absent identity must return 401 on management APIs; public discovery remains anonymous.
8. Open the same draft in two signed-in tabs. Save/publish in A, then try the stale action in B: 409/reload guidance. Validate max < min, duplicate/invalid dates, negative preparation and invalid mode: no partial writes or publication.

Keep this increment uncommitted until the user finishes manual review. Afterwards commit 04/04a on the existing feat/15-property-management branch; do not close Issue #15 until phase acceptance is complete.
