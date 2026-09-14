---
id: sql-chat
title: SQL integration and saved chat history
description: How Canopy proves local SQLite use and persists conversations.
---

# SQL integration and saved chat history

## From CSV to SQLite

When a table is selected, Canopy loads the CSV with pandas and synchronizes it into `storage/canopy.sqlite`. The database registry records the source name, SQL table, row count, column count, and synchronization time. The synchronization code also checks that the physical SQL table exists, so a stale registry row cannot hide a missing table.

FVS data is stored in a table named `dataset_fvs_output_07222026`. Questions run against that table rather than repeatedly scanning the CSV.

## Parameterized queries

Canopy does not execute arbitrary model-generated SQL. It maps supported language to an allow-listed column, operator, and value, then binds the values separately.

For example:

```sql
SELECT *
FROM "dataset_fvs_output_07222026"
WHERE "Age" > ? AND "TCuFt" > ?
ORDER BY "MU_ID"
```

Bound parameters:

```json
[60.0, 3000.0]
```

The Streamlit interface exposes the database path, table name, executed SQL, parameters, and returned row count under **SQL and data proof**. This is the simplest way to demonstrate that SQLite—not an in-memory imitation—is producing the result.

## Persistent conversations

Chats are stored in two relational tables:

```text
chat_conversations
  id (primary key)
  dataset_key
  title
  created_at
  updated_at

chat_messages
  conversation_id + position (composite primary key)
  message_blob
  created_at
```

The selected dataset is part of the chat key, so inventory, raster, and FVS conversations remain separate. Each `message_blob` is a compressed serialized message containing its role, text, and—where applicable—the structured FVS query result specification. When Canopy starts, it reloads those messages from SQLite. When an old FVS chat is opened, Canopy reruns the stored specification and reconstructs its table, chart, polygon map, or raster overlay.

This design avoids storing large dataframes or image blobs inside chat history while preserving a reproducible record of what was asked and how it was answered.

## What proves persistence

1. Ask a question and note the **Saved in SQLite** message count in the sidebar.
2. Stop Streamlit completely.
3. Start Canopy again with `./run_canopy.sh`.
4. Select the same dataset and saved chat title.
5. The prior question, explanation, query evidence, chart, and map are rebuilt from SQLite.
