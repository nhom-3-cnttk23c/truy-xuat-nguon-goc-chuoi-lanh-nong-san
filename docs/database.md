# Database security and ownership

- Alembic migrations run with the migration database URL. The runtime role is a
  separate role with NOSUPERUSER and NOBYPASSRLS.
- Tenant tables use PostgreSQL row level security. Request context is set with
  transaction-local set_config.
- RLS derives organization and inspector role from the active, unrevoked session
  whose hash is in the transaction context. It does not trust caller-set
  organization or role values.
- The application role has read-only access to lots. A composite foreign key
  guarantees that a lot's farm belongs to the same organization.
- The application role has append-only access to events (GRANT SELECT, INSERT;
  REVOKE UPDATE, DELETE ON events).
- PostgreSQL triggers `trg_events_prevent_update` and `trg_events_prevent_delete`
  invoke `prevent_event_mutation()` to reject any UPDATE or DELETE statement with
  an integrity violation exception at the database engine level (N3-21).
- Farm names, areas, and coordinates have database constraints as well as API
  validation.

CI upgrades an empty database, checks Alembic metadata, downgrades to base, then
upgrades again before running PostgreSQL integration tests.

