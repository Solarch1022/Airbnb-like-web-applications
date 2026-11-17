# Property management — Phase 2 / Notion 03

GitHub: https://github.com/Solarch1022/Airbnb-like-web-applications/issues/15
Notion: https://app.notion.com/p/3f78a059477280c59a99ff4b1710b806

## MVP decisions for this increment

- Properties belong to an organisation. `created_by` is audit information, not a separate owner permission or platform admin role.
- Active organisation admins create, edit, archive and delete eligible drafts. Active members read/list all properties in their organisation, including drafts and archived history.
- Create as `DRAFT` with a title. Details may be completed incrementally; supplied values must be valid. Prices are positive Decimal amounts with at most two fractional digits, normalised to two digits. Currency is an uppercase three-letter code; supported-currency policy is part of provisioning.
- `booking_mode` may be unset on a draft. There is no implicit INSTANT default. INSTANT and REQUEST are validated and persisted when explicitly supplied. Task 04 must require an explicit valid mode at publication and implement its remaining configuration/readiness rules. Existing-booking snapshots and approval behaviour belong to the booking phases.
- The archive API supports `DRAFT → ARCHIVED` and preserves records. Archived properties remain readable by members and cannot be edited. There is no publication, reactivation or ownership-transfer endpoint yet.
- Admins may permanently delete DRAFT or ARCHIVED records only when they were never published and have no booking history. The page offers both Archive (retain the record) and Delete draft (permanently remove it) for eligible drafts. A version-checked transaction removes the property row and writes a permanent deletion marker; it does not remove the original creation request/audit snapshot. Repeated DELETE after success returns 404. No existing user drafts are deleted automatically by this implementation.
- `published_at` and `has_booking_history` are server-controlled, monotonic history guards. Task 04 must set published_at atomically at first publication. Booking creation must set has_booking_history atomically with the booking and include the property/version/lifecycle guards. Neither field may be cleared by cancellation or archival. A published/booking-referenced property must remain archival-only. There is no booking table in 03, so this does not pretend to inspect future booking records; these guards are the explicit integration contract for subsequent tasks. Existing 03 records predate publication/bookings and safely default to unpublished/no history.
- Management reads always require authentication. Drafts and archived records have no public read route. Task 04 will add separate publication-controlled responses/discovery; management schemas must not be reused as public responses.
- This is an implementation baseline for review, not a claim that all proposed lifecycle/product decisions were approved by the supervisor.

## API

Base: `/organisations/{organisation_id}/properties`

| Method | Path | Access | Result |
|---|---|---|---|
| POST | base | Admin | 201, original creation snapshot; requires Idempotency-Key |
| GET | base?limit=20&cursor=... | Member/admin | items + next_cursor |
| GET | base/{property_id} | Member/admin | Full management record |
| PATCH | base/{property_id} | Admin | Updated DRAFT; requires expected_version in body |
| DELETE | base/{property_id}?expected_version=1 | Admin | Archived record; HTTP 200, no physical deletion |
| DELETE | base/{property_id}/draft?expected_version=1 | Admin | Permanently delete an eligible draft; HTTP 204 with empty body |

Create example:

```json
{"title":"Perth apartment","price_per_night":"120.50","currency":"AUD","max_guests":2,"booking_mode":"REQUEST","images":["https://example.com/apartment.jpg"]}
```

PATCH example:

```json
{"description":"Near the city centre","expected_version":1}
```

Editable fields: title, description, address, property_type, price_per_night, currency,
max_guests, images and booking_mode. Omitted PATCH fields remain unchanged. Explicit
null clears optional fields; title and images cannot be null (use [] to clear images).
Unknown fields and client-controlled identity, organisation, creator, status, timestamps
or version/history guards are rejected. `expected_version` is the concurrency precondition, not a
replacement version. Prices use exact decimal strings in JSON and storage. Image
references accept HTTP/HTTPS URLs only, up to 20; no upload, fetching or image-content
verification is implemented in 03.

## Permission and error policy

Identity → active organisation membership → actual scoped property lookup → admin
requirement for writes. IDs are always looked up with both organisation_id and
property_id. A property ID from another organisation therefore returns the same
404 as a missing ID in an accessible organisation.

- 401: invalid/missing authentication.
- 403: inaccessible/inactive organisation, missing/inactive membership, insufficient role, or permission revoked before a transaction commits.
- 404: property absent from the permitted organisation.
- 409: stale version, attempted edit of an archive, ineligible draft deletion (published/booking history), changed payload with a reused key, or retryable transaction conflict.
- 410: original POST key refers to a permanently deleted draft. Use a new key only when intentionally creating a new property.
- 422: invalid payload, missing idempotency key/version, invalid limit/cursor.
- Operational database errors propagate; they are not disguised as permission/conflict errors.

## Persistence, retries and concurrency

- `properties`: partition key organisation_id, sort key property_id (Strings).
- `property_creation_requests`: partition key request_id (String).
- Table names are configurable by DYNAMODB_PROPERTIES_TABLE_NAME and DYNAMODB_PROPERTY_REQUESTS_TABLE_NAME.
- Local startup creates tables when AUTO_CREATE_TABLE=true outside production. Production tables require separate provisioning.
- Listing uses a consistent Query with limit 1–100. The response cursor wraps the last key and organisation; it must be reused unchanged with the same organisation. It is not an authorisation token. Archived rows remain in the management list. Pages are not a frozen snapshot of concurrent changes.
- Creation keys use the Phase 1 syntax (1–128 ASCII letters/digits/dot/underscore/colon/hyphen), scoped to caller + organisation. Keep the same key and normalised payload when retrying. A transaction writes the property and creation response together. Replays return the original creation snapshot even after edits/archive; GET returns the latest state. After permanent deletion, replays of the original creation key return 410 instead of resurrecting or returning a successful snapshot. The deletion marker shares the requests table under a separate `deleted:<organisation_id>:<property_id>` key; existing creation records remain compatible without a table migration. Records have no TTL. Normalisation strips surrounding whitespace and fixes the price scale; image order remains meaningful.
- Every mutation transaction checks ACTIVE account, ACTIVE organisation and ACTIVE admin membership. Updates condition on the existing DRAFT and expected version before replacing the row; successful edits/archive increment version once. Concurrent edit/archive attempts from the same snapshot have at most one winner.
- Repeating archive with the current archived version returns the same record. A stale version returns 409, including when another call already archived it; reload before retrying. Existing booking data is never mutated.

## Management page

Use the existing `/management` sign-in and organisation selection. Admins see Create
property, Edit, Archive and Delete draft for eligible DRAFT records; archived drafts offer View and Delete draft. Members see View only. List pagination uses Load more. The form
retains entered values after failures. Reload properties closes the editor; reopen the
latest record after 409. Confirm permanent deletion before submitting; canceling the confirmation makes no request. Archive has its own confirmation explaining that the record and history are retained; Delete draft confirms irreversible removal. UI content uses textContent,
not HTML insertion. Changing organisation discards the visible editor and suppresses
late list/detail responses from the previous context.

Creation retry keys are retained in page memory by organisation and payload until a
successful response. Retry unchanged details after an uncertain failure; changing the
payload constitutes a new creation attempt. Reload/sign-out clears keys and tokens, so
cross-reload recovery requires callers to retain their own key. Automatic token refresh,
server-session revocation and durable editor recovery remain outside this increment.

## Automated verification

From the repository root:

```bash
.venv/bin/python -m pytest tests/test_property.py tests/test_property_dao.py -v
docker compose up -d dynamodb-local
.venv/bin/python -m pytest tests/integration/test_properties_integration.py -v
.venv/bin/python -m pytest tests -v
git diff --check
```

Integration tests use randomly named isolated test tables and remove only those tables.
They verify real serialisation, exact prices/URL lists, create rollback under revoked
access, concurrent duplicate submissions, concurrent edit/archive, pagination and
organisation scope. Skips are not proof of passing database checks.

## Manual verification

1. Start DynamoDB Local and the API on different ports:

   ```bash
   docker compose up -d dynamodb-local
   DYNAMODB_ENDPOINT_URL=http://localhost:8000 AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AUTO_CREATE_TABLE=true .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
   ```

2. Open http://localhost:8080/management, sign in with an existing local account,
   select/create an organisation, and create a draft using just a title. Reopen it,
   fill in details and mode, save and verify version increments. Invalid URLs/prices
   should show validation feedback without losing input.
3. Open the same property in two signed-in browser tabs. Save tab A; saving the stale
   tab B must return a conflict. Reload properties, reopen the record, then save again.
4. Create a draft and choose Archive: it must remain as ARCHIVED with View (and Delete draft if eligible), without Edit or a second Archive button. Create a disposable draft, choose Delete draft, and cancel the confirmation: it must
   remain. Confirm deletion: it must disappear; GET and a repeated DELETE return 404.
   Replaying its original POST key must return 410. Existing archived drafts without
   publication/booking history must also offer Delete draft. The archive API continues
   to preserve history and rejects PATCH on an archive.
5. Use two existing accounts/organisations in Swagger or API calls to verify 403/404
   policy. The MVP has no invitation or public role-edit endpoint; member cases are
   covered by automated tests unless a member fixture already exists locally.
6. With the same Idempotency-Key and payload, POST twice: same original response and
   one property. Change the payload using that key: 409. Try list?limit=1 and follow
   next_cursor; another organisation's properties must never appear.
7. Anonymous management APIs must return 401. No draft should be publicly readable
   or bookable. Publication and booking acceptance remain for tasks 04 and 05–08.

## Commit boundary

This increment includes Notion 03 plus the property-permission portion of 01. Keep
01's booking permissions tracked for later phases. After manual verification, a
suggested commit is `feat(property): implement organisation-scoped property CRUD`.
Complete 04/04a in subsequent commits on the same Issue #15 branch; open the Phase 2
PR only after the whole phase meets its acceptance criteria.


## Draft deletion acceptance

- Only an active admin of the actual organisation may delete, with the current expected_version.
- The transaction rechecks account, organisation, membership, version, allowed status, absent published_at and absent/false has_booking_history.
- Editing or acquiring a publication/booking reference concurrently prevents stale deletion. Failed deletion leaves both the property and its creation retry behaviour intact.
- The property row is removed; a deletion marker and original creation snapshot remain for retry/audit consistency. There is no application restore action.
- Old archived drafts created before the history fields existed can be removed without migration. The code does not remove the two existing manual-test drafts; the user can select which to keep.
