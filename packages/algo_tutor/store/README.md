# algo_tutor/store

The SQLite database: the SQLAlchemy models, the schema version (kept in
`PRAGMA user_version`), the rows seeded from files, and daily backups.
`timeutil.py` defines how times and dates are written to the database.

To change the schema, add a `_step_N` migration to `migrations.py` and update
`models.py` to match.
