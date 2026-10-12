> Tài liệu lịch sử. Xem [tình trạng nghiệm thu hiện hành](../ACCEPTANCE.md).

# Sprint 2 staging backend — incident report

Updated: 08/10/2026

## Verified

- Group `main` is at `8899474`. The frontend deployment succeeded; the backend deployment for that commit failed.
- The live OpenAPI document still exposes `GET /lots`, `GET/POST /events`, and `GET/POST /products`. It is missing `POST /lots`, both event history/integrity methods, and all six handover methods.
- In the staging UI, `grower@caudat.vn` reaches the handover page but receives `Not Found`; the product catalogue is empty, so lot creation cannot proceed.
- `admin@mocchau.vn` is shown as `system_admin`, although the current seed/migration chain restores it to `organization_admin`.
- The connected Render account cannot read the AgroChain service or its logs. The exact live database revision has not been queried.

## Likely cause

The historical pre-Sprint 2 migration at revision `20261007_08` upgraded the Mộc Châu admin role. Sprint 2 reused that same revision ID for harvest-lot columns. Alembic tracks revision IDs, so a database already stamped at the historical `20261007_08` can skip the new lot schema and fail when revision `20261007_09` uses `quantity` and `harvested_on`.

The role and API symptoms are consistent with this collision, but without the live database state or Render startup logs this remains a diagnosis to verify.

## Source repair in progress

- Keep `20261007_08` as a compatibility marker for the historical release.
- Move harvest-lot schema to unique revision `20261008_15`, before the handover migration.
- Make revision 15 reconcile existing columns, constraints, indexes, and policy safely, so both old and partially upgraded databases can proceed.
- CI simulates both a legacy revision 08 with no harvest schema and a revision 08 where harvest schema already exists.

No production or staging database has been manually stamped, reset, or modified.

## Rollout

After this repair passes CI and merges, Render should deploy from group `main`. Confirm the backend deployment, all 11 Sprint 2 OpenAPI contracts, and demo role boundaries. If deploy still fails, inspect the Render build/startup logs and actual migration table before attempting any database repair.

Do not run the earlier draft's `UPDATE alembic_version` or schema-reset SQL without a verified database snapshot and a tested recovery plan.
