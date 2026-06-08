# Assigned Message Values Backlog

This note reserves the future design for per-recipient message values such as
invite codes, coupons, pass numbers, and personal links.

## Current Preparation

The `contacts` table stores only the latest assignment summary:

- `last_assigned_code`
- `last_assigned_label`
- `last_assigned_at`

These fields are intentionally hidden from the contact create/edit UI for now.

## Future Tables

```sql
CREATE TABLE IF NOT EXISTS message_value_pools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_name TEXT NOT NULL,
    pool_type TEXT,
    source_type TEXT,
    memo TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS message_value_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id INTEGER NOT NULL,
    item_value TEXT NOT NULL,
    item_label TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'unused',
    assigned_contact_id INTEGER,
    assigned_send_list_id INTEGER,
    assigned_campaign_id INTEGER,
    assigned_at TEXT,
    used_at TEXT,
    memo TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Suggested item statuses:

- `unused`
- `assigned`
- `used`
- `skipped`
- `void`

## Future Send Snapshot Fields

The send recipient snapshot has reserved fields:

- `assigned_value`
- `assigned_value_label`
- `assigned_value_pool_id`
- `assigned_value_item_id`

## Future Message Variables

Start with one canonical variable:

```text
{assigned_value}
```

Aliases can be added later if needed:

```text
{assigned_code}
{coupon_code}
```
