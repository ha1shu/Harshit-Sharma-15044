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
