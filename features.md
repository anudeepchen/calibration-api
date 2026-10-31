# Features and API reference

[Documentation index](README.md) · [Quick start](quickstart.md)

Endpoint contracts, request examples, validation, and current versus historical membership behavior.

## Features

| Capability | Behavior |
| --- | --- |
| Create calibrations | Store a generated UUID, type, exact decimal value, username, and measurement timestamp. |
| Add tags | Start a membership period; adding an already active tag returns the existing membership unchanged. |
| Remove tags | End the active period without deleting history; removing an inactive tag succeeds as a no-op. |
| Search calibrations | Combine exact user/type, measurement time, and current or historical tag filters. |
| List tags | Return current tags or tags associated with a calibration at a supplied timestamp. |
| Historical queries | Use stored membership intervals with inclusive starts and exclusive ends. |
| Concurrent mutations | Serialize tag changes for each calibration with PostgreSQL row locks. |

There is no authentication, frontend, seed job, separate tags table, calibration
update/delete endpoint, or full membership history endpoint. The application does
not create database tables at startup: schema changes run through Alembic.

## API reference and examples

Set a base URL for the examples:

```sh
API_URL=http://localhost:8000
```

### Create a calibration

```sh
curl -i -X POST "$API_URL/calibrations" \
  -H 'Content-Type: application/json' \
  -d '{
    "calibration_type": "offset",
    "value": "1.25000000000000000001",
    "username": "alice",
    "recorded_at": "2026-09-15T10:00:00Z"
  }'
```

Returns HTTP 201 with a representation such as:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "calibration_type": "offset",
  "value": "1.25000000000000000001",
  "username": "alice",
  "recorded_at": "2026-09-15T10:00:00Z"
}
```

Copy the actual returned UUID for subsequent requests:

```sh
CALIBRATION_ID=replace-with-the-returned-uuid
```

`recorded_at` is optional and defaults to the current UTC time. `username` and
`calibration_type` are trimmed and must remain nonblank. Values use Python Decimal
and unconstrained PostgreSQL NUMERIC. Send decimal strings for exact precision;
responses serialize values as JSON strings. JSON integers and finite fractional
numbers such as `1.25`, `-0.3`, and `101.3` are also accepted for compatibility
with the assignment's sample data. Fractional JSON numbers are decoded to Python
floats before validation, then converted using `Decimal(str(value))`, avoiding
the binary expansion produced by `Decimal(float)`. This cannot recover decimal
digits already lost during JSON decoding: use strings whenever the sender's
exact decimal representation matters. Booleans, null, invalid numeric strings,
NaN, and infinities are rejected. Precision is subject to PostgreSQL's native
NUMERIC limits.

### Add a tag

```sh
curl -i -X POST "$API_URL/calibrations/$CALIBRATION_ID/tags" \
  -H 'Content-Type: application/json' \
  -d '{"tag":"production-ready"}'
```

Returns HTTP 201 for a new period, or HTTP 200 with the same membership ID and
addition timestamp if the tag is already active:

```json
{
  "id": "a421c6a7-9b60-453d-9e08-a69e76ad994f",
  "calibration_id": "550e8400-e29b-41d4-a716-446655440000",
  "tag": "production-ready",
  "added_at": "2026-10-01T10:00:00Z",
  "removed_at": null
}
```

The timestamp above is illustrative: actual membership timestamps are always
controlled by the service. Save the returned `added_at` to try a snapshot query
at the exact addition boundary.

### List current or historical tags

```sh
curl "$API_URL/calibrations/$CALIBRATION_ID/tags"
curl --get "$API_URL/calibrations/$CALIBRATION_ID/tags" \
  --data-urlencode 'as_of=2026-10-01T12:00:00Z'
```

Returns HTTP 200 with distinct, case-sensitively sorted names:

```json
{"tags":["production-ready"]}
```

A calibration with no matching memberships returns `{"tags":[]}`. Use an actual
membership timestamp to see the membership created in your local workflow;
the fixed example time may precede it.

### Search calibrations

```sh
curl --get "$API_URL/calibrations" \
  --data-urlencode 'username=alice' \
  --data-urlencode 'calibration_type=offset' \
  --data-urlencode 'from_time=2026-09-01T00:00:00Z' \
  --data-urlencode 'to_time=2026-10-01T00:00:00Z' \
  --data-urlencode 'tag=production-ready' \
  --data-urlencode 'tag_as_of=2026-10-01T12:00:00Z' \
  --data-urlencode 'limit=50' \
  --data-urlencode 'offset=0'
```

This asks for Alice's offset calibrations measured during September that belonged
to the tag at noon UTC on October 1. All supplied filters use AND semantics.

| Parameter | Rules |
| --- | --- |
| `username` | Exact match after trimming; blank is invalid. |
| `calibration_type` | Exact match after trimming; blank is invalid. |
| `from_time` | Inclusive lower bound on measurement time. |
| `to_time` | Exclusive upper bound on measurement time; must exceed `from_time` when both are present. |
| `tag` | Exact, case-sensitive tag match after trimming. |
| `tag_as_of` | Historical membership snapshot; requires `tag`. Omit for current membership. |
| `limit` | Default 50; accepted range 1–100. |
| `offset` | Default 0; must be nonnegative. |

The response contains `items`, `limit`, and `offset`, with no total count. Results
are ordered by `recorded_at DESC, id DESC`, including a deterministic tie-breaker.
Historical filtering uses EXISTS so multiple membership periods cannot duplicate
a calibration. Offset pages can shift when other requests insert calibrations.

### Reproduce a historical search with your own timestamps

After creating the September calibration above and setting `CALIBRATION_ID`, this
example captures an actual membership timestamp, removes the tag, and retrieves
the calibration using its earlier membership together with measurement bounds:

```sh
MEMBERSHIP=$(curl --fail --silent --show-error -X POST "$API_URL/calibrations/$CALIBRATION_ID/tags" \
  -H 'Content-Type: application/json' -d '{"tag":"review-snapshot"}')
TAG_AS_OF=$(printf '%s' "$MEMBERSHIP" | python -c 'import json,sys; print(json.load(sys.stdin)["added_at"])')
curl --fail --silent --show-error -X DELETE --get "$API_URL/calibrations/$CALIBRATION_ID/tags" \
  --data-urlencode 'tag=review-snapshot'
curl --fail --silent --show-error --get "$API_URL/calibrations" \
  --data-urlencode 'username=alice' \
  --data-urlencode 'calibration_type=offset' \
  --data-urlencode 'from_time=2026-09-01T00:00:00Z' \
  --data-urlencode 'to_time=2026-10-01T00:00:00Z' \
  --data-urlencode 'tag=review-snapshot' \
  --data-urlencode "tag_as_of=$TAG_AS_OF"
```

The final response includes the calibration even though that tag is now inactive.
Omitting `tag_as_of` instead returns only current members of `review-snapshot`.

### Remove a tag

```sh
curl -i -X DELETE --get "$API_URL/calibrations/$CALIBRATION_ID/tags" \
  --data-urlencode 'tag=production-ready'
```

Returns HTTP 204 with no body. Repeating the request is an idempotent no-op.
Re-adding the tag later creates a new membership row; it does not modify or
replace the earlier period.

### Error responses

| Status | Meaning |
| --- | --- |
| 404 | A tag operation references an unknown calibration. |
| 422 | Invalid UUID, blank text, invalid decimal, missing required input, naive/invalid timestamp, invalid time range, or pagination validation failure. |
| 409 | A database integrity constraint rejected the transaction; the response contains a generic conflict message. |

Errors use FastAPI's `detail` field. Validation errors generally contain an array
of field errors; domain errors contain a message. Database integrity exceptions
are rolled back and raw database messages are not returned to clients.

## Time and historical membership semantics

All accepted timestamps must include a timezone, for example `Z` or `+02:00`.
The API normalizes timestamps to UTC for storage/serialization; PostgreSQL stores
timezone-aware instants and may display them in the database session timezone.
When using positive offsets in query strings, URL-encode the `+` using
`--data-urlencode` as in the examples.

There are two independent notions of time:

1. **Measurement time** (`calibrations.recorded_at`): supplied by the caller or
   defaulted to current UTC. Search time bounds apply to this field only.
2. **Membership time** (`added_at` / `removed_at`): generated by this service
   when tags change. Snapshot queries apply to these fields only.

A membership is active at timestamp T when:

```sql
added_at <= T AND (removed_at IS NULL OR removed_at > T)
```

For example, after adding at 10:00, removing at 11:00, and re-adding at 12:00:

| Snapshot time | Membership |
| --- | --- |
| Before 10:00 | Absent |
| Exactly 10:00 through just before 11:00 | Present |
| Exactly 11:00 through just before 12:00 | Absent |
| Exactly 12:00 onward, until another removal | Present |

Intervals are half-open: addition is inclusive, removal is exclusive. Current
membership means `removed_at IS NULL`. Future snapshots are allowed and reflect
the currently known membership state, not predictions of later changes. History
records service mutations, not inferred membership at measurement time.
A period can have equal addition/removal timestamps; its interval is empty.
