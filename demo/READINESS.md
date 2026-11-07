# Interview readiness review — 7 November 2026

The local Python/Windows demonstration is ready to rehearse. Container execution,
remote CI, and SAP ABAP execution are **not verified as passing**. This is an
educational SAP Utilities-inspired project, not SAP IS-U/IDEX or a compliant GPKE
implementation.

## Scope and findings

Reviewed the accumulated working-tree changes on
`feature/swe-interview-improvements`, based on commit
`22aa23f8493520609040b690cb433775b325cdbe`: database configuration, Compose,
isolated tests, message error handling, supplier simulation, migration, ABAP
rounding/tests, and documentation. No unrelated application changes were found.
The ABAP demo and public signatures remain intact. This review did not change
ABAP or Python business logic, commit, push, or access the real application database.

Corrections and additions in this review:

| File | Purpose |
| --- | --- |
| `.gitignore` | Ignore SQLite files, sidecars, migration backups, and `.env` so demo data does not accidentally enter Git. |
| `.dockerignore` | Exclude databases, backups, Git, virtual environments, caches, and local settings from the Docker build context. |
| `docker-compose.yml` | Bind all published ports to localhost; preserve the database URL and existing named volume. |
| `.github/workflows/ci.yml` | Add feature-branch pushes, explicit read-only permissions, module-based pytest invocation, and Compose configuration validation. |
| `tests/test_services.py` | Strengthen migration checks to preserve existing billing/readings/messages and changed suppliers/history; test transactional schema rollback; close sample SQLite connections explicitly. |
| `demo/Invoke-Demo.ps1` | Repeatable HTTP demonstration, unique IDs, current UTC switch dates, assertions for success and expected rejection/error responses. |
| `demo/Start-Demo.ps1` | Start a hidden API process with a temporary database and loopback port, run the demo, stop its process, restore the environment, retain logs/data. |
| `README.md` | Architecture diagram, Windows setup, API examples, demo instructions, simulation explanation, and explicit limitations. |
| `demo/READINESS.md` | This evidence and handover report. |

## Checks actually executed

| Check | Observed result |
| --- | --- |
| `ruff check app tests` | Passed. |
| `python -m pytest -q` | **34 passed** in the final code test run. |
| `git diff --check` | Passed. |
| `python -m pytest --collect-only -q` | Confirmed 34 cases; collection alone is not counted as execution. |
| PowerShell parser checks for both demo scripts | Passed on Windows PowerShell **5.1.26100.9818**. |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File demo/Start-Demo.ps1 -Repeat` | Passed twice against the same isolated database and live Uvicorn HTTP server. |
| Read-only SQLite inspection after demo server shutdown | Confirmed two customers/meters, six readings, two EUR 168.39 invoices, two completed and two rejected switches, and two completed and two failed messages. Failed reasons were `Meter does not exist`; no failed-message readings were inserted. |
| Migration CLI subprocess, `python -m app.migrate_supplier_switches`, twice with an isolated legacy `DATABASE_URL` | Passed; legacy meter retained with `DEFAULT`; two distinct backups; SQLite integrity checks passed for the migrated database and an inspected backup. Temporary sample only. |
| YAML parse and assertions for CI triggers/permissions/steps | Passed; not a GitHub workflow execution or a complete Actions schema validation. |
| `docker compose config --quiet` and rendered JSON inspection | Passed. Confirmed SQLite absolute URL, `/app/data` named-volume mount, localhost ports, and monitoring paths. Used an empty temporary Docker config to bypass restricted access to the user's Docker configuration. |
| `docker version` | Client installed; daemon connection failed (`docker_engine` pipe absent). |
| `docker build -t utilities-platform:readiness .` | Initial attempt blocked by Docker config access; retry with temporary `--config` reached the missing-daemon error. **No image build completed.** |
| GitHub Actions REST reads | Five historical runs inspected: all `startup_failure`; inspected CI run had no jobs, and HEAD had no check-run output. No passing remote run verified. |

No Docker containers were started, so container restart persistence, Prometheus
scraping, and Grafana runtime behavior were not tested. No ABAP Unit tests were
executed because no SAP ABAP runtime was available. No dependency vulnerability
scanner, penetration test, load test, or PowerShell 7 run was performed.

### Every executed pytest case

All cases below passed. Bracketed variants represent separate executed cases.

| Test name | Variants / purpose | Count |
| --- | --- | ---: |
| `test_complete_meter_to_bill_flow` | Customer, meter, two readings, EUR 168.39 bill | 1 |
| `test_reject_decreasing_reading` | Reading API rejects decrease | 1 |
| `test_idoc_success` | Completed message and committed reading | 1 |
| `test_idoc_missing_fields` | Missing segment, meter ID, date, reading | 4 |
| `test_idoc_invalid_reading` | Unknown meter, duplicate date, decrease, earlier date, negative value | 5 |
| `test_idoc_inactive_meter` | Inactive meter rejection stored | 1 |
| `test_idoc_duplicate_transaction` | Existing completed and failed messages | 2 |
| `test_idoc_database_failure_rolls_back_reading` | Real flush failure, rollback, stored error, subsequent success | 1 |
| `test_supplier_switch_success_and_history` | Two switches and original history preserved | 1 |
| `test_supplier_switch_rejection` | Unknown customer/meter, old-supplier mismatch, same supplier, past/future dates | 6 |
| `test_supplier_switch_meter_eligibility` | Wrong owner and inactive meter | 2 |
| `test_supplier_switch_duplicate_id` | Previously completed and rejected IDs | 2 |
| `test_supplier_switch_malformed_input` | Invalid date syntax, blank supplier, empty request ID | 3 |
| `test_supplier_switch_rollback` | History write failure rolls back supplier; session reusable | 1 |
| `test_meter_explicit_supplier` | Optional initial supplier and existing response structure | 1 |
| `test_sqlite_supplier_migration_preserves_data` | Backup, existing rows, repeat migration, retained supplier and history | 1 |
| `test_sqlite_migration_rolls_back_schema_failure` | Failed table creation also rolls back added column; backup retained | 1 |
| **Total** | | **34** |

## Remote CI investigation

The latest recorded push run is
[29711981379](https://github.com/DarshanBakilanaRamesh/smart-meter-utilities-devops/actions/runs/29711981379).
The inspected named CI/manual run is
[29711885655](https://github.com/DarshanBakilanaRamesh/smart-meter-utilities-devops/actions/runs/29711885655).
Both refer to the existing `22aa23f` commit and report `startup_failure`.
The other recorded runs, `29711635040`, `29711626688`, and `29711501979`, also
report `startup_failure`. Their dates are 20 July 2026; they do not validate the
uncommitted review work.

The local YAML has no obvious structural problem. Previously, direct pushes to
this feature branch were excluded by the branch filter; that is now corrected.
This filter does not explain the historical main/manual startup failures. The
returned job/check data did not expose their cause. Review the linked run's UI and
repository/account Actions settings before the interview; a successful run of the
final code is still needed after the owner chooses to publish it. This review did
not trigger a remote workflow or change account settings.

## Exact rehearsal commands

Run from the project root in Windows PowerShell. First-time setup:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Isolated demonstration (recommended; no existing application database touched):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\demo\Start-Demo.ps1 -Python .\.venv\Scripts\python.exe -Repeat
```

For an existing API, or to keep Swagger open while presenting, start the API in
one terminal and invoke the demo in another. These commands use the configured
application database and add demo records:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Second terminal, same project directory:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\demo\Invoke-Demo.ps1 -BaseUrl http://127.0.0.1:8000
```

Open `http://127.0.0.1:8000/docs`. For an older SQLite schema, stop the API and
follow the README's backup/migration instructions first. Do not migrate the real
database just to rehearse; the isolated launcher creates a new schema automatically.

Repeat local checks with the new environment:

```powershell
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Once Docker Desktop is running with Linux containers, pending container checks:

```powershell
docker compose config --quiet
docker build -t utilities-platform:readiness .
docker compose up --build -d
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\demo\Invoke-Demo.ps1 -BaseUrl http://127.0.0.1:8000
docker compose up -d --force-recreate api
# After API readiness, retrieve a printed switch ID to verify its persistence.
```

Do not run `docker compose down -v` if you want to retain the database.

## Remaining limitations to explain in the interview

- Local educational prototype: no authentication/authorization, TLS, rate limits,
  or production credential handling. Compose is now localhost-only, but Grafana
  still uses `admin/admin`; container processes use the image's default user.
- No SAP connection or real GPKE process. Supplier requests complete immediately
  only for today's UTC date; business rejections return HTTP 201 with `REJECTED`.
- Billing is fixed-tariff and not idempotent: repeated calculation creates new
  bill records. Reading storage has three decimal places, with no explicit input
  precision limit. Timestamps are UTC by convention without an offset suffix.
- SQLite migration is offline/additive and SQLite-specific. No concurrency/load
  guarantees, database-lock retry, or recovery worker for crash-interrupted
  `RECEIVED` messages. Persistent database failure may prevent failure logging.
  SQLite foreign-key enforcement is not explicitly enabled.
- Dashboard summary does not include switching counts; failed message detail is
  stored in SQLite but has no GET endpoint. Monitoring volumes are not persistent.
- Docker runtime checks, successful remote CI, and SAP activation/ABAP Unit are
  outstanding. Passing Python checks does not validate ABAP syntax or execution.
