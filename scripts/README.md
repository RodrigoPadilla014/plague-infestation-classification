# Scripts

Scripts are runnable helpers.

- `diagnostics/` — run SQL diagnostics and write reports under `tmp/`
- `loaders/` — load supporting source tables into PostgreSQL

Keep feature definitions in `sql/`. Scripts should mostly read SQL, execute it,
and write artifacts or summaries.
