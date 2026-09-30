# TODO

Working list for upcoming sessions. Requirements live in [Docs/SRD](Docs/SRD/README.md);
IDs in brackets point there.

## Panels and breaker positions [PNL-001 to PNL-012]

- [x] Panel table and channel breaker columns: migration `0002_panels` [PNL-001, PNL-002]
- [x] Pure layout rules: occupied spaces, same-column check, overlap check [PNL-003, PNL-004]
- [x] `GET/POST/PATCH/DELETE /panels`, channel PATCH accepts panel, space, poles, amps [PNL-002, PNL-007]
- [x] Device detail page: breaker column and editor with single / double / triple pole [PNL-005]
- [x] Panel view page: spatial layout, live power per breaker, empty spaces, list alternative [PNL-006]
- [x] One sensor per pole on multi-pole breakers (A2 on space 1, B2 on space 3), per-leg draw in the panel view [PNL-002, PNL-004]
- [x] Mains strip at the top of the panel: A1 / B1 with V, W and today's kWh, plus total [PNL-010]
- [x] Every space shows voltage plus W or A, toggled per page and kept in the URL (`?show=amps`) [PNL-011]
- [ ] Rebuild and redeploy the API image so the live stream sends `phase_label` (mains show `—` until then)
- [ ] Explicit mains assignment for subpanels [PNL-012]
- [ ] Try it end to end while signed in: add a panel, place channels, check the panel view with live data
- [ ] DB integration tests for the panel endpoints (needs the DB test harness below)
- [ ] Load as a share of breaker rating, flag above 80 % [PNL-008]
- [ ] Breakers with no CT, tandem breakers, printable panel directory [PNL-009]

## Fixes

- [x] Channels hidden as `unused` at setup stayed hidden after a role change, so connected C1 to C6 showed no live data. Role change now sets visibility, device page has a Shown checkbox, migration `0004` un-hides affected channels [CIR-001, CIR-002]

## Carried over

- [ ] Billing engine [SRD 05]
- [ ] Export (CSV, JSON, XLSX) and schedules [SRD 06]
- [ ] Alerts [ALR-*]
- [ ] DB integration test harness; backend coverage is 53 % against the 80 % target [NFR-030]
- [ ] Kiosk tokens [RBAC-009]
- [ ] Move login throttle to the database before running more than one API replica
