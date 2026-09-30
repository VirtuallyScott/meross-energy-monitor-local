# Meross EM16P API Discovery Notes

How the API was found, what was actually tested and what is still open. Date: 2026-09-28. Target: `192.168.2.75`.

## 1. Method

1. **Page inspection.** The web UI at `http://192.168.2.75/` is a single page Svelte app. The whole bundle (~840 KB) is **inline in one `<script>` tag**. No external JS files were loaded. The only other resource was `/assets/loading_img.png`.
2. **Network capture.** Chrome's network log showed no XHR or fetch traffic during auto refresh. That was the first hint that the data comes over a WebSocket.
3. **Bundle analysis.** Searched the inline script for `WebSocket`, `.request(` call sites, route strings and auth code. Found:
   - `new WebSocket(\`ws://${window.location.hostname}/rpc\`)`
   - A client class whose `request(method, params)` sends `{id, src, method, params, auth?}` frames
   - 33 literal method names (listed in the spec)
   - Login code that builds a SHA-256 digest response with realm = `dev_id`
4. **Live verification.** Opened separate WebSocket and HTTP connections from the page and called **read-only** methods only.

## 2. What was called live

| Method | Transport | Result |
|---|---|---|
| `Refoss.DeviceInfo.Get` | WS, GET, POST | OK. `auth_en: false` |
| `Refoss.Status.Get` | GET, WS | OK |
| `Refoss.Config.Get` | GET | OK |
| `Sys.Config.Get` | GET | OK |
| `Cloud.Config.Get` | GET | OK |
| `Em.Chmerge.List` | GET | OK |
| `Em.Data.Get` | POST, GET with query string | OK with params. Tested windows of 2.5 min, 1 h, 6 h and 1, 7 and 30 days back |
| `Em.Data.Get` with `id: 130` (merge mask) | POST | Envelope with no `result` |
| `Em.Data.Get` with no params | GET, POST | Error text / no `result` |
| `Webhook.List` | GET | Empty list |
| `Webhook.Supported.List` | GET | Event list |
| `Timer.List`, `Schedule.List`, `OverTemp.Config.Get` | GET | `invalid namespace` |
| `Refoss.ListMethods`, `Sys.ListMethods` | GET | `invalid namespace` |
| `Nope.Get` (made-up method) | POST | Connection dropped, fetch failed. Device stayed up (next call succeeded) |
| `WiFi.Scan.List` | GET | Did not return within the call timeout. Abandoned |

**Not called** (they change state or are destructive): every `*.Set`, `*.Create`, `*.Update`, `*.Del`, `*.Delete`, `Refoss.Device.Reboot`, `Refoss.Factory.Reset`, `Refoss.Upgrade`, `Refoss.Upgrade.Check`, `Refoss.Auth.Set`, `Sys.Time.Update`, `Em.Data.Del`.

## 3. Observations worth keeping

- **Refoss under the hood.** RPC namespaces are `Refoss.*`, CSS classes are `refoss-*`, the session storage key is `refoss_route` and the UI has model branches for `em06p` and `em16p`. The EM16P appears to be a Refoss EM16P with Meross branding. Refoss documentation or community projects for the EM16P may carry over, but check before relying on them.
- **Shelly Gen2 lineage.** Frame format, `src`/`dst` addressing, `/rpc/<Method>` GET form, digest auth and `NotifyStatus`/`NotifyEvent` all match Shelly Gen2. Shelly tooling concepts transfer, but `Shelly.*` method names do not.
- **Shared UI code.** The bundle includes switch, cover, input, timer and schedule screens from sibling products. That explains methods that return `invalid namespace` here.
- **Notification gating.** A fresh socket gets no pushes until it sends a request. After that, `NotifyStatus` arrived at roughly 16 s intervals across two samples, and one `NotifyEvent` was seen right after connecting.
- **History cap.** `Em.Data.Get` returns 60 one-minute rows at most. A 6 hour request returned the first hour plus a `next_ts`.
- **Short history.** All period counters (`day`, `week`, `month`, `year`) matched each other and uptime was about 7.8 h. That points to a recent install or reset, which is why older history ranges were empty.
- **Merge mask decode** confirmed against UI labels: `130 → em:2 + em:8` (A2 + B2, Waterfall Pool Pump), `1040 → em:5 + em:11`, `2080 → em:6 + em:12`.
- **Phase C unused.** `em:13` to `em:18` read ~0.09 V.
- **MQTT half configured.** `enable: true`, `rpc_ntf: true`, but status `connected: false`.

## 4. Open questions

1. **Overview formula.** What exactly makes up "Consumption", "Generation" and "Grid Exchange" on the overview? It is close to `em:1 + em:7`, but the bundle wasn't traced far enough to confirm whether it uses channel roles, a setting or fixed channels. The `⚠` next to Grid Exchange was not investigated.
2. **History retention.** How many days or months of minute data the device keeps. Re-test after it has been running a week.
   - 2026-09-29 re-test: `Em.Data.Get` for `em:1` returned full hours back to about 34 h ago and a partial hour at 35 h; nothing older. Uptime was 32.4 h, so minute history **survives a reboot**. The oldest row lines up with install time, so the retention limit is not reached yet. Device clock skew vs. host: 0 s.
3. **`Refoss.Auth.Set` params.** Needed to turn auth on from a script. Easiest way to capture it: set a password in the web UI with the network log open (the WS frame shows in DevTools → Network → WS → Messages).
4. **Auth on GET.** Whether `/rpc/<Method>` GET accepts a digest `Authorization` header once auth is on, or if only POST and WS frames work.
5. **Webhook condition fields.** Threshold and comparison fields for `em.power_change` and the others. Capture by creating one in the UI.
6. **MQTT topics.** Actual topic names once a broker is connected.
7. **`NotifyEvent` payload.** Capture a few and document the event types.
8. **`WiFi.Scan.List` behavior.** Whether it is slow or needs to be called twice (start the scan, then read results).
9. **`Refoss.Status.Get` over HTTP GET while auth is on** for simple monitoring tools that can't do digest.

## 5. How to re-run discovery after a firmware update

Paste into the DevTools console on `http://<host>/`:

```js
// List every literal RPC method the UI calls.
const t = document.scripts[0].textContent;
[...new Set(t.match(/\.request\(["'`][^"'`]+["'`]/g))]
  .map(x => x.slice(10, -1)).sort().join("\n");
```

```js
// Live notification sampler (20 s).
const ws = new WebSocket(`ws://${location.hostname}/rpc`);
ws.onopen = () => ws.send(JSON.stringify({id: 1, src: "probe", method: "Refoss.DeviceInfo.Get"}));
ws.onmessage = e => console.log(JSON.parse(e.data));
setTimeout(() => ws.close(), 20000);
```

Compare the method list against section 4 of the spec. Any new names are candidates to document.
