# SRD 07 — Non-Functional Requirements, Testing and Acceptance

## 1. Performance

Reference hardware: 4-core x86 or Raspberry Pi 5 with 8 GB RAM and SSD. Reference load: 10 devices, 12 active channels each, 2 years of history, 5 concurrent users.

| ID | Pri | Requirement |
|---|---|---|
| NFR-001 | M | Live samples appear in the browser within 3 s of the device notification (p95). |
| NFR-002 | M | History chart for one circuit over 30 days returns in under 500 ms; over 1 year at daily resolution under 1 s (p95, server time). |
| NFR-003 | M | Bill estimate for one cycle computes in under 2 s; 12-cycle comparison of 3 plans under 15 s. |
| NFR-004 | M | Collector keeps up with 20 devices on 256 MB RAM and under 10% of one CPU core on average. |
| NFR-005 | M | Backfill after a 24 h outage completes within 15 minutes for 10 devices, without exceeding COL-007 per-device limits. |
| NFR-006 | M | Front end meets Core Web Vitals on the reference LAN: LCP < 2.5 s, INP < 200 ms, CLS < 0.1. JS bundle under 300 KB gzipped for the initial route; charting library loaded on demand. |
| NFR-007 | M | Minute-resolution export of 1 year for 10 circuits completes in under 5 minutes with bounded memory (EXP-006). |

## 2. Reliability and data integrity

| ID | Pri | Requirement |
|---|---|---|
| NFR-010 | M | No minute data is lost when the collector restarts, provided the device still holds it (COL-005). |
| NFR-011 | M | Minute energy captured versus device period counters (`day_energy`) differs by less than 0.5% per channel per day when there were no gaps. Verified by a nightly consistency check that raises a data-quality event. |
| NFR-012 | M | All services restart automatically on failure (Swarm restart policy). The app recovers without manual action after a host reboot. |
| NFR-013 | M | Database backups succeed nightly; a failed backup raises an alert. |
| NFR-014 | S | Target availability of the UI 99% per month, excluding planned upgrades. Collection continues when the API or web tier is down. |
| NFR-015 | M | Recovery point objective 24 h (nightly backup); recovery time objective 1 h using the documented restore. |

## 3. Security

Covered in [04-rbac-security.md](04-rbac-security.md). Release gates in §6.

## 4. Usability and accessibility

| ID | Pri | Requirement |
|---|---|---|
| NFR-020 | M | WCAG 2.2 AA. Every chart has a data-table alternative and text summary. |
| NFR-021 | M | Works in current Chrome, Firefox, Safari and Edge, desktop and mobile, from 320 px wide. |
| NFR-022 | M | Units always shown (W, kW, kWh, V, A, currency). Local time zone of the site shown on time axes. |
| NFR-023 | M | Adding a first device, assigning a flat rate and seeing today's cost takes under 5 minutes for a new user following the UI alone. |
| NFR-024 | S | Honors `prefers-reduced-motion` and `prefers-color-scheme`. |

## 5. Maintainability and operations

| ID | Pri | Requirement |
|---|---|---|
| NFR-030 | M | Test coverage at least 80% lines for backend, and at least 95% for the billing engine and the device protocol client. |
| NFR-031 | M | Lint, format and type checks in CI: `ruff`, `mypy --strict` for backend; ESLint, Prettier and `tsc --noEmit` for frontend. |
| NFR-032 | M | CI builds multi-arch images, runs all tests, runs dependency and image scans (SEC-052), and publishes images tagged with the version and git SHA. |
| NFR-033 | M | Install guide, upgrade guide, backup and restore guide, and a device hardening guide (auth on, IoT VLAN, DHCP reservation) ship with v1. |
| NFR-034 | M | Configuration is documented in one reference table: every env var, secret and setting with default and effect. |

## 6. Test strategy

| ID | Pri | Level | Scope |
|---|---|---|---|
| TST-001 | M | Unit | Billing engine: every component kind, every netting mode, tiers with both allocations, proration, rounding, bank carry, true-up. Worked examples E1–E7 in SRD 05 are required fixtures. Property-based tests (Hypothesis) for invariants: total equals sum of line items; zero usage gives only fixed charges; doubling a flat rate doubles energy lines. |
| TST-002 | M | Unit | Device protocol client: envelope parsing, missing `result`, non-JSON bodies, `next_ts` pagination, bitmask decode, digest response computation against a known vector, allow-list enforcement. |
| TST-003 | M | Unit | Time handling: DST spring and fall days in at least `America/New_York` and `Europe/London`, a half-hour offset zone (`Asia/Kolkata`), cycles crossing year end, seasons wrapping year end, TOU rules crossing midnight. |
| TST-004 | M | Unit | RBAC: matrix test generated from §1.4 of SRD 04. For each role and scope, every route is called and allowed/denied as expected. Includes out-of-scope 404 and token-subset rules. |
| TST-010 | M | Tool | **Device simulator**: an HTTP and WebSocket server that mimics EM16P responses from the API spec, including quirks (notifications after first request, 60-row cap, empty `emmerge`, dropped connection on unknown method, optional digest auth, configurable outages and clock skew). Used by integration and E2E tests and by the dev compose file. |
| TST-011 | M | Integration | Collector against the simulator and a real TimescaleDB (Testcontainers): live ingest, backfill after outage, idempotent re-ingest, gap recording, advisory-lock exclusivity with two collectors. |
| TST-012 | M | Integration | API against a real database: every endpoint's success and validation paths, pagination, `If-Match` conflicts, export streaming, SSRF rejection cases (SEC-040/041). |
| TST-013 | M | Integration | Migrations: upgrade from the previous release's schema with seeded data. |
| TST-020 | M | E2E | Playwright critical flows: first-run setup; add device (simulator); set channel roles; create a virtual circuit; see live power; create a TOU plan and assign it; view bill estimate; export CSV; Viewer cannot see admin pages; kiosk token view. |
| TST-021 | S | E2E | Visual regression at 320, 768, 1024 and 1440 px in light and dark themes for overview, history, bill and device pages. Automated accessibility scan (axe) on each page. |
| TST-022 | S | Performance | Load test with a seeded 2-year dataset and 10 simulated devices to verify NFR-001 to NFR-007. |
| TST-030 | M | Operational | Backup and restore drill into a fresh stack; verify row counts and a sample bill match. |
| TST-031 | M | Hardware | Before release, run the collector against at least one real EM16P for 72 hours, compare daily kWh with the device UI, and confirm open questions Q4 and Q5 from SRD 00. |

## 7. Delivery phases (proposed)

| Phase | Content | Exit criteria |
|---|---|---|
| P0 Foundations | Repo, CI, stack skeleton, DB + migrations, auth, RBAC core, device simulator | Deploys on a single-node Swarm; login works; RBAC matrix test green |
| P1 Collection | Device registry, credentials, collector (live + backfill), channels, circuits, device health | 72 h run against simulator with no data loss; TST-011 green |
| P2 Visualization | Overview, live, history, breakdown, device detail, panels and breaker positions with mains strip and per-space V + W/A readings (PNL) | NFR-001, NFR-002 met |
| P3 Billing | Rate plan model and editor, engine, cycles, estimate, projection, comparison, cost per circuit | TST-001 green including E1–E7 |
| P4 Export and alerts | Exports, schedules, alert rules and channels | TST-020 flows green |
| P5 Hardening | Backups, TLS options, audit viewer, docs, performance and security passes, real-device run | All §8 criteria met |

## 8. Release acceptance criteria (v1)

1. All **Must** requirements in SRDs 01–07 are implemented, or explicitly waived in writing by the product owner.
2. All **[UNVERIFIED-API]** items used by Must requirements are verified on real hardware or the related feature is disabled by default with a UI note.
3. CI green: tests, coverage thresholds (NFR-030), lint, types, scans with no critical or high findings.
4. RBAC matrix test and SSRF tests pass.
5. Backup and restore drill (TST-030) passes.
6. 72-hour real-device run (TST-031) shows under 0.5% daily kWh variance versus the device.
7. Install, upgrade, restore and hardening guides reviewed by someone who did not write them.

## 9. Traceability

Each requirement ID must be referenced by at least one test name or test docstring (for example `test_bil_034_hourly_netting`). A CI script lists Must requirement IDs from the SRD files that no test references.
