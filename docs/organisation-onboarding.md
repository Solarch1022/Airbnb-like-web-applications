# Organisation onboarding (Phase 1 / Notion 02)

Notion: https://app.notion.com/p/3c38a059477280859303c21c786fd27f
GitHub phase: #14

## Agreed MVP rules

- Any authenticated ACTIVE account can create an organisation.
- The creator receives ACTIVE admin membership only in that organisation.
- Roles are `admin` and `member`; neither grants platform-wide administrator access.
- Organisation names may repeat; IDs identify organisations.
- Invitations and self-service joining of an existing organisation are outside this MVP. Memberships from a future authorised invitation flow can use the same schema/dependencies. There is no public role-assignment endpoint.
- Creating an organisation requires `Idempotency-Key` (1–128 ASCII letters, digits, `.`, `_`, `:`, `-`). Reuse the same key and normalised payload on retries. Reusing a key with different details returns 409. Keys are scoped to the caller and records persist without expiry. Replays return 201 with the original context while membership and organisation remain active.

## API

| Method | Route | Access / result |
|---|---|---|
| GET | `/me/organisations` | Authenticated; list caller's active organisation contexts |
| POST | `/organisations` | Authenticated; atomically create organisation, admin membership and retry record |
| GET | `/organisations/{organisation_id}` | Active organisation member |
| GET | `/organisations/{organisation_id}/admin` | Active admin in the requested organisation |
| GET | `/management` | Public sign-in shell; all data/API actions require authentication |

Creation body: `{"name":"My Organisation"}`. Extra fields such as `role`, `created_by` and `organisation_id` are rejected. The caller identity comes from `get_current_user`.

## Permission matrix

| Operation | Anonymous | Active account, no membership | Active member | Active admin |
|---|---|---|---|---|
| Open sign-in shell | Yes | Yes | Yes | Yes |
| List own organisations | No | Yes (possibly empty) | Yes | Yes |
| Create a new organisation | No | Yes | Yes | Yes |
| Read selected organisation | No | No | Yes | Yes |
| Read admin management context | No | No | No | Yes |

Membership and role are checked separately for each requested organisation. Inactive/missing organisations and inactive/missing memberships return a generic 403. Invalid authentication returns 401. Database operational failures are not converted into permission failures.

Property and booking permissions remain in phases 2–4. No property count is invented before the property model exists.

## Persistence and recovery

DynamoDB tables (configurable):

- `organisations`: partition key `organisation_id` (String).
- `organisation_memberships`: partition key `account_id`, sort key `organisation_id` (Strings). Listing uses a paginated query, not a table scan.
- `organisation_creation_requests`: partition key `request_id` (String), a SHA-256 of caller + idempotency key; stores the payload fingerprint and created organisation ID.

A single transaction checks that the creator account is still ACTIVE, then conditionally writes the organisation, membership and idempotency record. These writes succeed or fail together. Concurrent duplicate submissions read the winning result or receive a retryable 409. Unknown/operational DynamoDB failures propagate rather than being disguised as conflicts.

With `AUTO_CREATE_TABLE=true` outside production, startup creates these tables and the previously missing session table. Production tables must be provisioned separately.

## Management page

Open `/management` on the running API server. Sign in with an existing account, choose an organisation or create one, then see the selected context. Admins see first-property guidance; members see a message directing them to their admin. Property creation itself belongs to task 03 and is visibly marked as forthcoming.

Tokens remain in page memory only; reload/sign-out clears local access. Page sign-out does not revoke the existing server session. An expired access token requires signing in again; automatic refresh/session revocation are outside this change. A failed create submission retains its retry key in page memory for another attempt with the same name; callers needing retries across reloads must retain their key.

## Validation

```bash
.venv/bin/python -m pytest tests/test_authentication.py tests/test_organisation.py tests/test_organisation_dao.py -v
.venv/bin/python -m pytest tests --ignore=tests/integration -v
.venv/bin/python -m pytest tests/integration/test_organisations_integration.py -v
```

The integration suite requires DynamoDB Local and tests real transaction rollback, retry and concurrent duplicate submissions. A skipped integration test is not evidence of successful database validation.
