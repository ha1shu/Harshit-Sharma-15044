I need to build a complete, production-quality full-stack project based on the problem statement I will provide below:


Friday night at the multiplex
The multiplex booking counter keeps mis-pricing tickets and the queue is getting angry. Seats come in tiers — Silver, Gold, Recliner — at different prices, and by showtime some tiers sell out and shouldn’t be bookable. There are offers on: a flat festival discount and a percentage off for members (capped). Every booking then adds a small per-ticket convenience fee and GST on top, and it all has to total to the exact paisa. Customers keep demanding a clear line-by-line breakup of the bill.
Build a pricing engine the counter can trust.
(The messy real-world money rules are the point — handle each correctly, and build it for any cinema counter, not one show. Get a plain booking total right first, then layer on the offers, the fee and the tax.)

----------------------------------------------
Your task is to first create a clear implementation plan only. Do not start coding yet.
Plan must cover:

1. Requirement Analysis – understand the problem, users, features, and expected workflow.
2. System Architecture – define frontend, backend, database, APIs, and how everything connects.
3. Technology Stack – recommend suitable technologies and briefly explain why.
4. Frontend Plan – pages/screens, components, navigation, forms, validation, state management, and responsive UI.
5. Backend Plan – API structure, authentication/authorization if required, business logic, validation, error handling, and security. (Python backend)
6. Database Plan – database choice, tables/collections, relationships, primary/foreign keys, indexes, and required queries.
7. Frontend ↔ Backend ↔ Database Connectivity – explain the complete data flow and API communication.
8. Project Structure – recommended folder/file structure for frontend and backend.
9. Core Features & User Flow – step-by-step workflow of how users interact with the system.
10. Testing Plan – unit, API, integration, and basic end-to-end testing.
11. Deployment Plan – how frontend, backend, and database will be deployed and configured.
12. Security & Production Readiness – environment variables, authentication, input validation, CORS, SQL injection protection, logging, etc.
13. Development Phases – divide the implementation into logical phases so the project can be built and tested incrementally.

Important:

* Keep the architecture practical and suitable for a real-world project.
* Avoid unnecessary technologies or overengineering.
* Prioritize clean code, scalability, maintainability, security, and good UI/UX.
* Clearly mention assumptions or missing requirements.



* At the end, provide a step-by-step execution roadmap that another coding agent can follow from setup → development → testing → deployment.

I will provide the actual problem statement next. Analyze it carefully and create the complete plan based on it.


please Creating the text which I copy to other ai agent.





# REASONING.md

## What the problem actually was

The brief is dressed up as a booking-counter app, but the counter/CRUD/UI parts are the easy 20%. The actual problem is a **billing engine**: given messy, tiered, discount-and-tax-laden real-world money rules, produce a bill that is correct to the paisa, explainable line-by-line, and trustworthy enough that a manager can hand it to an angry customer without flinching. Everything else in the system — cinemas, screens, shows, seats, the UI — exists to feed inputs into that engine and store its output. So the first decision was to treat the **pricing engine as the product**, and treat the booking counter as its delivery mechanism.

That shaped the build order directly: get a plain multi-tier subtotal exactly right first, then add discounts, then the fee, then tax — each stage fully tested before the next was layered on, rather than writing one big `calculate_total()` function and trying to get every rule right simultaneously. A bug in "does the flat discount apply before or after the percentage cap" is much easier to find and reason about when each stage is a separate, independently-tested function than when it's buried inside a 60-line endpoint handler.

## Why the pricing engine is a pure, isolated module

`pricing/engine.py` takes plain data in (prices, quantities, discount config, tax config) and returns a structured breakup out. It doesn't import SQLAlchemy, doesn't know about FastAPI, doesn't touch a session or a request object. Two reasons:

1. **Testability.** Money bugs are almost always edge-case bugs (a discount that exceeds the subtotal, a cap that kicks in at exactly the boundary, a rounding tie at .005). Those are cheap to enumerate and assert against when the function under test is pure — no database fixtures, no auth tokens, no HTTP layer in the way. The bulk of the test suite lives here for exactly this reason.
2. **Correctness under change.** If the engine could reach into the database itself, it would be tempting to let it "peek" at a seat's availability or a booking's history mid-calculation, which quietly couples pricing correctness to database state at calculation time — the exact kind of coupling that produces "it worked on my machine" pricing bugs. Keeping it pure means the *only* way prices can be wrong is if the inputs handed to it are wrong, which is a much smaller, more auditable surface.

## Why `Decimal`, not `float`, everywhere

Floats are binary fractions; money is decimal. `0.1 + 0.2 != 0.3` in IEEE-754, and multiplying that error across ticket quantities and percentage discounts compounds it. The brief explicitly says "total to the exact paisa" — that sentence alone rules out floats as a valid implementation choice, not just a style preference. `Decimal` in Python and `NUMERIC` in Postgres were chosen together so the type never has to cross a lossy boundary between application code and storage.

## Why rounding happens per-stage, and the total is the sum of already-rounded lines

The alternative — compute everything in full precision and round only the final total — is what most naive implementations do, and it's exactly what produces the classic complaint: "your line items say ₹203.05 but the total says ₹203.06, where did that paisa come from?" Rounding each stage (discount, fee, each tax component) to 2 decimals as it's produced, and then defining the grand total as the *sum of those already-rounded numbers* rather than a separately-rounded full-precision sum, guarantees the displayed breakup always reconciles exactly with the displayed total. That invariant — `sum(line_items) == total` — is asserted directly in the test suite as a property, not just checked incidentally, because it's the single thing a customer at the counter is most likely to manually verify with a calculator.

## Why the discount stacking order was fixed the way it was

The brief leaves stacking order genuinely ambiguous — "a flat festival discount and a percentage off for members" doesn't say which applies first or whether they combine at all. Rather than silently picking one, I fixed it explicitly and documented it as a configurable rule, not a hardcoded accident:

- Flat discount first, off the raw subtotal.
- Percentage discount second, off the *post-flat-discount* amount.
- The percentage discount's cap is applied to the discount amount itself, not to the resulting total.
- The discounted subtotal floors at ₹0 — a booking can never go negative because a discount happened to exceed the price.

The reasoning for flat-before-percentage: it's the more customer-favorable order in the common case (percentage-off-a-smaller-base means a smaller rupee discount than percentage-off-the-full-subtotal would give), and it's also how most real ticketing platforms visibly behave, so it matches customer expectation rather than surprising them. This is flagged as an assumption, not asserted as objectively correct, because the brief doesn't actually specify it — a different, equally defensible interpretation exists, and the config is structured so it can be flipped without touching the engine's code.

## Why the convenience fee is taxable, and what base GST is computed on

Multiplex ticketing in practice (BookMyShow and similar platforms) charges GST on the convenience fee as well as the ticket price — it's a service charge, not a pass-through cost, so it's part of the taxable supply. I matched that real-world convention rather than inventing a different one, but made it a toggle in the tax config rather than baking the assumption into the engine, since a different cinema chain's actual tax treatment could legitimately differ and I didn't want that decision to require a code change.

## Why seat inventory uses an atomic conditional update instead of a naive check-then-write

The naive version — `SELECT available_seats`, check in application code, then `UPDATE` — has an obvious race: two counters booking the last Recliner seat simultaneously can both pass the check before either writes. The fix used here is a single atomic statement:

```sql
UPDATE seat_tiers
SET available_seats = available_seats - :qty
WHERE id = :tier_id AND available_seats >= :qty
RETURNING available_seats;
```

If zero rows come back, the booking is rejected with a clear error inside the same transaction as the booking insert, and the whole transaction rolls back — so a failed seat-decrement never leaves an orphaned booking row behind. This was chosen over row-level `SELECT ... FOR UPDATE` locking because it's simpler, doesn't hold a lock for the duration of the pricing calculation, and Postgres already guarantees the update itself is atomic — the condition and the write happen as one indivisible operation, so there's no window for a second request to slip in between "check" and "write."

## Why bookings freeze their own breakup (`breakup_json`) instead of recomputing on read

If a booking's invoice were recalculated on every page view using current prices/offers, then changing a price or deactivating an offer tomorrow would silently rewrite yesterday's invoices — which is both wrong (the customer was charged what they were charged) and operationally dangerous (it destroys the audit trail the whole project exists to provide). Storing the full computed breakup at the moment of booking, and always reading that frozen copy back rather than recomputing, means historical invoices are immutable by construction, not by convention someone has to remember to follow.

## Why Postgres, not SQLite or an in-memory store, for the real implementation

Three concrete requirements ruled out anything lighter:
1. Exact `NUMERIC` decimal columns, not floating-point storage.
2. Real transactional guarantees for the atomic seat-decrement above — this needs to be safe under genuine concurrent load, which SQLite's single-writer model doesn't model realistically.
3. The explicit README note that "database tests should use PostgreSQL, not SQLite" reflects a decision made early: testing against a different engine than production risks passing tests against behavior (locking, numeric precision, constraint enforcement) that doesn't match what actually ships.

## Why the CSV import feature is "preview, then explicit commit," not "upload and apply"

The import feature's whole point is trustworthiness — it exists because the counter has been mis-pricing tickets, so an import path that silently overwrites tier prices with bad data would recreate the exact problem the project is solving. The two-step flow (`/import/preview` returns a full report and writes nothing; `/import/apply?confirm=true` requires an explicit confirmation) means an admin always sees exactly what will change — imported, de-duplicated (with which value won and why), rejected (with a specific reason per row) — before anything touches the database. This mirrors the same principle used for bookings: never trust unvalidated input enough to act on it immediately, always re-surface it for confirmation first.

The **last-valid-duplicate-wins** tie-break rule was chosen over "first wins" or "highest wins" because it matches the most common real-world reason a spreadsheet has duplicate tier rows — someone re-pasted a corrected value further down the file. It's stated explicitly (in code and in the README) rather than left implicit, because a silent, undocumented tie-break rule is just a different flavor of the mis-pricing bug this project is trying to eliminate.

Case-insensitive matching with a normalized Title Case storage form (`Silver`, not `SILVER`/`silver`) exists because tier identity is semantic, not textual — "Silver" and "SILVER" are the same tier typed by two different people, and treating them as different tiers would silently fragment inventory and pricing across two rows for what the business considers one seat class.

A price of `0` is accepted, not rejected, because it's a legitimate business case (a complimentary/comp tier) rather than malformed data — the cleaning rules exist to catch genuinely bad input (blank, negative, unparseable), not to second-guess a valid pricing decision an admin might actually want to make.

## Why the shipped UI is server-rendered HTML instead of the React SPA in the original plan

The original implementation plan proposed a React + Vite SPA talking to a REST API, which is a reasonable default for a counter application. During the build, I moved to server-rendered FastAPI + templates instead, for a narrower reason than "SPA vs. server-rendered" as a general preference: this app's actual interaction surface — pick a show, pick tiers, toggle two offers, see a bill, confirm — doesn't need client-side routing, optimistic UI, or complex client state management to feel responsive. A server-rendered page with a small amount of JS for the live bill-breakup recalculation gets the same UX with meaningfully less surface area: no separate frontend build/deploy pipeline, no API-contract drift between two codebases, no client-side state that can get out of sync with server truth. Given the brief's own instruction to avoid unnecessary technology and overengineering, and that the hard problem was always the pricing logic rather than the UI architecture, this was the more defensible choice for what actually got built — it's a deliberate scope decision, not a shortcut.

## Where I made a call instead of asking, and why

The brief is intentionally underspecified on several money rules (discount stacking order, whether the convenience fee is taxable, the exact GST split, the CSV tie-break rule). Rather than blocking on those or guessing silently, each one was:
1. Resolved with an explicit, defensible default.
2. Implemented as configuration, not a hardcoded literal, so it can be corrected without touching the pricing engine's logic.
3. Documented in one place (this file, the plan, and the README) so the reasoning is visible to whoever reviews it, instead of being an invisible assumption baked into the code.

## Known gaps, stated plainly rather than hidden

Some things are intentionally out of scope for this pass rather than missed by accident: there's no documented flow yet for creating a cinema/screen/movie from scratch (only updating an existing show's tiers/pricing), no cancel-booking endpoint despite the schema supporting a `CANCELLED` status, and the tax config (GST rate/split) isn't exposed for editing in Admin. None of these affect the correctness of the pricing engine itself, which is why they were deprioritized behind getting the money math and the seat-concurrency handling right — but they're real gaps, and worth closing before this goes further than a demo.

cd /workspaces/Harshit-Sharma-15044/backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt >/tmp/multiplex_pip.log && pytest -q tests/test_pricing_engine.py


× Building wheel for pydantic-core (pyproject.toml) did not run successfully.
  │ exit code: 1
  ╰─> [74 lines of output]
      Python reports SOABI: cpython-314-x86_64-linux-gnu
      Computed rustc target triple: x86_64-unknown-linux-gnu
      Installation directory: /home/codespace/.cache/puccinialin
      Rustup already downloaded
      Installing rust to /home/codespace/.cache/puccinialin/rustup
      warn: it looks like you have an existing rustup settings file at:
      warn: /home/codespace/.cache/puccinialin/rustup/settings.toml
      info: profile set to minimal
      info: setting default host tuple to x86_64-unknown-linux-gnu
      warn: Updating existing toolchain, profile choice will be ignored
      info: syncing channel updates for stable-x86_64-unknown-linux-gnu
      info: default toolchain set to stable-x86_64-unknown-linux-gnu
      Checking if cargo is installed
      cargo 1.98.1 (797e8a9bc 2026-08-05)
      Rust not found, installing into a temporary directory
      Running `maturin pep517 build-wheel -i /workspaces/Harshit-Sharma-15044/backend/.venv/bin/python3 --compatibility off`
      📦 Including license file `LICENSE`
      🍹 Building a mixed python/rust project
      🐍 Found CPython 3.14 at /workspaces/Harshit-Sharma-15044/backend/.venv/bin/python3
      🔗 Found pyo3 bindings
      📡 Using build options features, bindings from pyproject.toml
         Compiling target-lexicon v0.12.14
         Compiling python3-dll-a v0.2.10
         Compiling once_cell v1.19.0
         Compiling proc-macro2 v1.0.86
         Compiling unicode-ident v1.0.12
         Compiling pyo3-build-config v0.22.0
         Compiling quote v1.0.36
         Compiling syn v2.0.68
         Compiling autocfg v1.3.0
         Compiling heck v0.5.0
         Compiling libc v0.2.155
         Compiling num-traits v0.2.19
         Compiling version_check v0.9.4
         Compiling pyo3-ffi v0.22.0
         Compiling pyo3-macros-backend v0.22.0
         Compiling rustversion v1.0.17
      error: failed to run custom build command for `pyo3-ffi v0.22.0`
      
      Caused by:
        process didn't exit successfully: `/tmp/pip-install-gpnvhswc/pydantic-core_04738a59de6744d7a10d5728f70b8791/target/release/build/pyo3-ffi-512c0575490ffe33/build-script-build` (exit status: 1)
        --- stdout
        cargo:rustc-check-cfg=cfg(Py_LIMITED_API)
        cargo:rustc-check-cfg=cfg(PyPy)
        cargo:rustc-check-cfg=cfg(GraalPy)
        cargo:rustc-check-cfg=cfg(py_sys_config, values("Py_DEBUG", "Py_REF_DEBUG", "Py_TRACE_REFS", "COUNT_ALLOCS"))
        cargo:rustc-check-cfg=cfg(invalid_from_utf8_lint)
        cargo:rustc-check-cfg=cfg(pyo3_disable_reference_pool)
        cargo:rustc-check-cfg=cfg(pyo3_leak_on_drop_without_reference_pool)
        cargo:rustc-check-cfg=cfg(diagnostic_namespace)
        cargo:rustc-check-cfg=cfg(c_str_lit)
        cargo:rustc-check-cfg=cfg(Py_3_7)
        cargo:rustc-check-cfg=cfg(Py_3_8)
        cargo:rustc-check-cfg=cfg(Py_3_9)
        cargo:rustc-check-cfg=cfg(Py_3_10)
        cargo:rustc-check-cfg=cfg(Py_3_11)
        cargo:rustc-check-cfg=cfg(Py_3_12)
        cargo:rustc-check-cfg=cfg(Py_3_13)
        cargo:rerun-if-env-changed=PYO3_CROSS
        cargo:rerun-if-env-changed=PYO3_CROSS_LIB_DIR
        cargo:rerun-if-env-changed=PYO3_CROSS_PYTHON_VERSION
        cargo:rerun-if-env-changed=PYO3_CROSS_PYTHON_IMPLEMENTATION
        cargo:rerun-if-env-changed=PYO3_PRINT_CONFIG
        cargo:rerun-if-env-changed=PYO3_USE_ABI3_FORWARD_COMPATIBILITY
      
        --- stderr
        error: the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)
        = help: please check if an updated version of PyO3 is available. Current version: 0.22.0
        = help: set PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 to suppress this check and build anyway using the stable ABI
      warning: build failed, waiting for other jobs to finish...
      💥 maturin failed
        Caused by: Failed to build a native library through cargo
        Caused by: Cargo build finished with "exit status: 101": `env -u CARGO PYO3_BUILD_EXTENSION_MODULE="1" PYO3_ENVIRONMENT_SIGNATURE="cpython-3.14-64bit" PYO3_PYTHON="/workspaces/Harshit-Sharma-15044/backend/.venv/bin/python3" PYTHON_SYS_EXECUTABLE="/workspaces/Harshit-Sharma-15044/backend/.venv/bin/python3" "cargo" "rustc" "--profile" "release" "--features" "pyo3/extension-module" "--message-format" "json-render-diagnostics" "--manifest-path" "/tmp/pip-install-gpnvhswc/pydantic-core_04738a59de6744d7a10d5728f70b8791/Cargo.toml" "--lib" "--crate-type" "cdylib"`
      Error: command ['maturin', 'pep517', 'build-wheel', '-i', '/workspaces/Harshit-Sharma-15044/backend/.venv/bin/python3', '--compatibility', 'off'] returned non-zero exit status 1
      [end of output]
  
  note: This error originates from a subprocess, and is likely not a problem with pip.
  ERROR: Failed building wheel for pydantic-core

[notice] A new release of pip is available: 25.3 -> 26.2.1
[notice] To update, run: pip install --upgrade pip
error: failed-wheel-build-for-install

× Failed to build installable wheels for some pyproject.toml based projects
╰─> pydantic-core

cd /workspaces/Harshit-Sharma-15044/backend && rm -rf .venv && python3.12 -m venv .venv && . .venv/bin/activate && pip install --upgrade pip >/tmp/multiplex_pip.log && pip install -r requirements.txt && pytest -q tests/test_pricing_engine.py
The virtual environment was not created successfully because ensurepip is not
available.  On Debian/Ubuntu systems, you need to install the python3-venv
package using the following command.

    apt install python3.12-venv

You may need to use sudo with that command.  After installing the python3-venv
package, recreate your virtual environment.

Failing command: /workspaces/Harshit-Sharma-15044/backend/.venv/bin/python3.12

pt-get update && apt-get install -y python3.12-venv
Reading package lists... Done
E: List directory /var/lib/apt/lists/partial is missing. - Acquire (13: Permission denied)
cd /workspaces/Harshit-Sharma-15044/backend && . .venv/bin/activate && PYTHONPATH=. python -m pytest -q tests/test_pricing_engine.py



_ test_calculate_booking_breakup[items3-festival_discount3-membership_percent3-membership_cap3-expected_total3] _

items = [('Silver', 2, Decimal('120.00'))], festival_discount = Decimal('50.00')
membership_percent = Decimal('10.00'), membership_cap = Decimal('30.00')
expected_total = Decimal('249.88')

    @pytest.mark.parametrize(
        "items, festival_discount, membership_percent, membership_cap, expected_total",
        [
            ([("Silver", 2, Decimal("120.00"))], Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("330.40")),
            ([("Silver", 2, Decimal("120.00"))], Decimal("50.00"), Decimal("0.00"), Decimal("0.00"), Decimal("271.40")),
            ([("Silver", 2, Decimal("120.00"))], Decimal("0.00"), Decimal("10.00"), Decimal("30.00"), Decimal("302.08")),
            ([("Silver", 2, Decimal("120.00"))], Decimal("50.00"), Decimal("10.00"), Decimal("30.00"), Decimal("249.88")),
        ],
    )
    def test_calculate_booking_breakup(items, festival_discount, membership_percent, membership_cap, expected_total):
        result = calculate_booking_breakup(
            line_items=items,
            festival_discount=festival_discount,
            membership_percent=membership_percent,
            membership_cap=membership_cap,
            convenience_fee_per_ticket=Decimal("20.00"),
            gst_rate=Decimal("0.18"),
        )
    
>       assert result["grand_total"] == expected_total
E       AssertionError: assert Decimal('248.98') == Decimal('249.88')

tests/test_pricing_engine.py:27: AssertionError
=========================== short test summary info ============================
FAILED tests/test_pricing_engine.py::test_calculate_booking_breakup[items3-festival_discount3-membership_percent3-membership_cap3-expected_total3] - AssertionError: assert Decimal('248.98') == Decimal('249.88')
1 failed, 5 passed in 0.04s

cd /workspaces/Harshit-Sharma-15044/backend && . .venv/bin/activate && PYTHONPATH=. python -m pytest -q tests/test_pricing_engine.py


docker compose up -d --build
docker compose down
docker compose down -v

cd backend
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/multiplex

PYTHONPATH=. python -m alembic upgrade head
PYTHONPATH=. python -m scripts.seed
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000

PYTHONPATH=. python -m alembic current
PYTHONPATH=. python -m alembic downgrade -1
PYTHONPATH=. python -m alembic revision --autogenerate -m "describe change"

PYTHONPATH=. pytest -q
PYTHONPATH=. pytest -q tests/test_pricing_engine.py
PYTHONPATH=. pytest -q tests/test_seat_tier_import.py

docker compose ps
docker compose logs --no-color --tail=100 api
docker compose logs --no-color --tail=100 db

curl http://127.0.0.1:8000/health
curl -I http://127.0.0.1:8000/dashboard
curl http://127.0.0.1:8000/api/shows/1
curl http://127.0.0.1:8000/api/bookings

lsof -nP -iTCP:8000 -sTCP:LISTEN
