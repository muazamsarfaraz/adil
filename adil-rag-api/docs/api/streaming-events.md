# Streaming Event Schema

`POST /api/v1/query/stream` emits Server-Sent Events (SSE) with the following event types.

Each event is framed as:

```
event: <type>
data: <json-or-string>

```

(blank line terminates the event)

## Event types

### `token`

A text chunk from the model. `data` is a JSON-encoded string.

```
event: token
data: "Based "
```

### `source`

A citation. `data` is a JSON object.

| Field | Type | Notes |
|-------|------|-------|
| `type` | `"statute" \| "case_law" \| "echr_judgment"` | enum |
| `title` | string | e.g. "Equality Act 2010 §10" |
| `url` | string | link to legislation.gov.uk or caselaw.nationalarchives.gov.uk |
| `citation` | string | e.g. `"[1]"` |
| `excerpt` | string (optional) | short quote |

### `viability`

A structured viability assessment. Emitted at most once, after all tokens.

| Field | Type |
|-------|------|
| `score` | int 0-100 |
| `vento_band` | `"Lower" \| "Middle" \| "Upper" \| "Exceptional"` |
| `statutory_footing` | bool |
| `case_law_precedent` | bool |
| `quantum_potential` | `"low" \| "moderate" \| "high"` |
| `evidence_checklist` | string[] |

### `done`

Terminal event. The stream will close after this.

| Field | Type |
|-------|------|
| `conversation_id` | string (UUID) or null |
| `sources_count` | int |
| `tokens_used` | int |

### `error`

Terminal event on failure.

| Field | Type |
|-------|------|
| `message` | string (human-readable) |
| `code` | `"RATE_LIMIT" \| "AUTH" \| "INTERNAL" \| "VALIDATION" \| "UPSTREAM"` |

## Keepalive

Between token bursts, the server may send SSE comments:

```
: keepalive

```

Clients should ignore comment lines.

## Example flow

```
event: token
data: "Based "

event: token
data: "in England, Section 10 [1] of the Equality Act 2010 protects..."

event: source
data: {"type":"statute","title":"Equality Act 2010 §10","url":"https://www.legislation.gov.uk/ukpga/2010/15/section/10","citation":"[1]"}

event: viability
data: {"score":75,"vento_band":"Middle","statutory_footing":true,"case_law_precedent":true,"quantum_potential":"moderate","evidence_checklist":["payslips","grievance letters"]}

event: done
data: {"conversation_id":null,"sources_count":1,"tokens_used":2450}
```

## Ordering guarantee

1. Zero or more `token` events
2. Zero or more `source` events (emitted after all tokens complete)
3. Zero or one `viability` event
4. Exactly one terminal event: `done` on success, `error` on failure
