# SRD 04 — RBAC and Security

## 1. RBAC model

### 1.1 Concepts

```
user ──< role_binding >── role ──< role_permission >── permission
             │
             └── scope: global | site:<site_id>
api_token ── owned by user, carries a subset of the owner's permissions, optional site restriction
```

- **Permission**: a `resource:action` string, for example `device:manage`. Permissions are fixed in code.
- **Role**: a named set of permissions. v1 ships built-in roles only. Custom roles are a Could (RBAC-030).
- **Role binding**: grants a role to a user at a **scope**. Global scope covers all sites. Site scope covers one site and everything in it (devices, channels, circuits, data, bills, alerts).
- **Effective permissions** = union of all bindings. There are no deny rules. Default is deny.
- **Global-only permissions** (`system:*`, `user:*`, `role:assign`, `audit:read`, `tariff:manage`) are ignored when granted at site scope.

### 1.2 Built-in roles

| Role | Intent |
|---|---|
| **Admin** | Full control: users, roles, system settings, backups, all sites. At least one active Admin must exist at all times. |
| **Site Manager** | Manages devices, credentials, circuits, rate-plan assignment and alerts for sites in scope. No user or system administration. |
| **Energy Analyst** | Reads everything in scope, runs bills, records actual bills, exports data, edits the shared tariff library when bound globally. Cannot change devices. |
| **Viewer** | Read-only dashboards, history and cost estimates for sites in scope. Can acknowledge alerts. No export. |
| **Kiosk** (token-only) | Read-only overview for one site. No login; used by wall displays through a kiosk token. |

### 1.3 Permission catalog

| Permission | Description | Global only |
|---|---|---|
| `system:settings` | Edit system settings, SMTP, retention, TLS options | yes |
| `system:backup` | Trigger, download, restore backups | yes |
| `system:health` | View health, metrics and job queue | no |
| `user:read` | List users and their bindings | yes |
| `user:manage` | Create, disable, reset users; reset MFA | yes |
| `role:assign` | Create and remove role bindings | yes |
| `audit:read` | View audit log | yes |
| `site:read` | View sites | no |
| `site:manage` | Create, edit, archive sites; set grid/solar/load circuits | no* |
| `device:read` | View devices, channels, status, events | no |
| `device:manage` | Add, edit, disable, delete devices in the registry; channel roles | no |
| `device:credential` | Set or clear the stored device password | no |
| `device:configure` | Write config to the device (names, CT factors, merges) | no |
| `device:reboot` | Reboot a device | no |
| `device:discover` | Run subnet discovery | yes |
| `circuit:read` | View circuits | no |
| `circuit:manage` | Create, edit, delete virtual circuits and tags | no |
| `data:read` | Live and historical readings | no |
| `data:export` | Export readings and bills; manage scheduled exports | no |
| `tariff:read` | View rate plans | no |
| `tariff:manage` | Create and edit rate plans in the shared library | yes |
| `tariff:assign` | Assign rate plans and billing cycles to a site | no |
| `bill:read` | View cost figures and bill estimates | no |
| `bill:run` | Run estimates, comparisons and what-if scenarios | no |
| `bill:actual` | Record actual utility bills for reconciliation | no |
| `alert:read` | View alerts | no |
| `alert:ack` | Acknowledge alerts | no |
| `alert:manage` | Create and edit alert rules and notification channels | no |
| `token:self` | Create and revoke own API tokens | no |

\* Creating a new site requires `site:manage` at global scope. Editing an existing site requires it at that site's scope.

### 1.4 Role to permission matrix

| Permission | Admin | Site Manager | Energy Analyst | Viewer | Kiosk |
|---|:-:|:-:|:-:|:-:|:-:|
| `system:settings`, `system:backup` | ✔ | | | | |
| `system:health` | ✔ | ✔ | | | |
| `user:read`, `user:manage`, `role:assign` | ✔ | | | | |
| `audit:read` | ✔ | | | | |
| `site:read` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `site:manage` | ✔ | ✔ | | | |
| `device:read` | ✔ | ✔ | ✔ | ✔ | |
| `device:manage`, `device:credential`, `device:configure` | ✔ | ✔ | | | |
| `device:reboot` | ✔ | | | | |
| `device:discover` | ✔ | | | | |
| `circuit:read` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `circuit:manage` | ✔ | ✔ | | | |
| `data:read` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `data:export` | ✔ | ✔ | ✔ | | |
| `tariff:read` | ✔ | ✔ | ✔ | ✔ | |
| `tariff:manage` | ✔ | | ✔ (global binding) | | |
| `tariff:assign` | ✔ | ✔ | | | |
| `bill:read` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `bill:run`, `bill:actual` | ✔ | ✔ | ✔ | | |
| `alert:read` | ✔ | ✔ | ✔ | ✔ | |
| `alert:ack` | ✔ | ✔ | ✔ | ✔ | |
| `alert:manage` | ✔ | ✔ | | | |
| `token:self` | ✔ | ✔ | ✔ | ✔ | |

### 1.5 Example

A homeowner is Admin. A partner is Viewer globally. A tenant in the guest cottage is Viewer bound to site "Cottage" only, so they see their own usage and cost and nothing from the main house. An electrician gets Site Manager on "Main house" for a week and the binding is removed afterwards.

### 1.6 RBAC requirements

| ID | Pri | Requirement |
|---|---|---|
| RBAC-001 | M | Every API endpoint declares the permission it needs. A test enumerates all routes and fails if any route has no declared permission or public marker. |
| RBAC-002 | M | Authorization is enforced in the API layer on every request, never only in the UI. The UI hides controls the user lacks permission for. |
| RBAC-003 | M | Queries for site-scoped resources are filtered to the user's permitted site ids. Requesting a resource outside scope returns `404`, not `403`, to avoid revealing it exists. |
| RBAC-004 | M | The last active Admin cannot be demoted, disabled or deleted. |
| RBAC-005 | M | Role binding changes take effect on the user's next request (no caching longer than the request). |
| RBAC-006 | M | Bindings can have an optional expiry (`expires_at`). Expired bindings are ignored and cleaned up by a job. |
| RBAC-007 | M | API tokens carry an explicit permission list that must be a subset of the owner's effective permissions at creation **and at use**. If the owner loses a permission, the token loses it too. |
| RBAC-008 | M | Tokens can be restricted to one site, have an expiry (default 90 days, max 1 year) and are revocable. Only a SHA-256 hash is stored; the token value is shown once. |
| RBAC-009 | M | A kiosk token is bound to one site, grants only the Kiosk role, and works only for the kiosk UI and its read endpoints. |
| RBAC-010 | S | Service tokens (not tied to a person, owned by an Admin) for integrations such as Home Assistant or Grafana. |
| RBAC-030 | C | Custom roles built from the permission catalog. |
| RBAC-031 | C | Postgres row-level security as defense in depth for site scoping. |

## 2. Authentication

| ID | Pri | Requirement |
|---|---|---|
| AUTH-001 | M | Local accounts with username or email and password. Passwords hashed with Argon2id (memory ≥ 64 MB, iterations ≥ 3). |
| AUTH-002 | M | Password policy: minimum 12 characters, maximum 128, checked against a bundled common-password list. No composition rules. |
| AUTH-003 | M | First-run setup: when no users exist, the API accepts creating the first Admin only with a one-time setup token read from a Docker secret or printed once to the API log. The endpoint is disabled after first use. |
| AUTH-004 | M | Login throttling: progressive delay per account and per source IP after 5 failures in 15 minutes. Failures return a generic message. |
| AUTH-005 | M | Sessions: random 256-bit id stored server-side, cookie `HttpOnly; Secure; SameSite=Strict`. Idle timeout 12 h, absolute 7 days. Session id rotated at login and privilege change. |
| AUTH-006 | M | Logout and "sign out all sessions" invalidate server-side sessions. Disabling a user kills their sessions and tokens. |
| AUTH-007 | S | TOTP multi-factor authentication with recovery codes. Admin can require it for Admin and Site Manager roles. |
| AUTH-008 | M | CSRF protection for cookie-authenticated state-changing requests: SameSite=Strict plus a synchronizer token header. |
| AUTH-009 | C | OIDC login (for example Authentik, Keycloak), with role bindings mapped from group claims. |
| AUTH-010 | M | API tokens use `Authorization: Bearer <token>`. Tokens are never accepted in query strings, except the kiosk token on the kiosk page URL. |

## 3. Device credential handling

| ID | Pri | Requirement |
|---|---|---|
| SEC-020 | M | Device passwords are encrypted with AES-256-GCM using a key from the `device_cred_key` Docker secret. The device row id is the associated data, so ciphertext cannot be moved to another device. |
| SEC-021 | M | Device passwords are write-only. The API returns only `has_password` and `password_updated_at`. |
| SEC-022 | M | Plaintext is decrypted only in the collector (and the API for "test connection") at use time and never logged, cached to disk or included in exports, error messages or backups in plaintext. |
| SEC-023 | S | Key rotation: ciphertexts carry a key version. A CLI command re-encrypts all credentials under a new key. |
| SEC-024 | M | Digest auth with the device uses the device's challenge nonce each time. The system never stores the derived `ha1`. |

## 4. Device command safety

| ID | Pri | Requirement |
|---|---|---|
| SEC-030 | M | The device client enforces a method allow-list in code. Anything else is rejected before it reaches the network. |
| SEC-031 | M | Each write method requires the permission listed and produces an audit entry with before and after values. |

| Method | Class | Permission |
|---|---|---|
| `Refoss.DeviceInfo.Get`, `Refoss.Status.Get`, `Refoss.Config.Get`, `Sys.Config.Get`, `Em.Data.Get`, `Em.Chmerge.List`, `Cloud.Config.Get`, `Webhook.List`, `Webhook.Supported.List` | Read | internal (collector) / `device:read` |
| `Em.Config.Set`, `Em.Chmerge.Create`, `Em.Chmerge.Update`, `Em.Chmerge.Del` | Write | `device:configure` |
| `Sys.Config.Set` (payload restricted to `device.name`) | Write | `device:configure` |
| `Refoss.Device.Reboot` | Write | `device:reboot` |
| `Refoss.Factory.Reset`, `Em.Data.Del`, `Refoss.Upgrade`, `Refoss.Upgrade.Check`, `Refoss.Auth.Set`, `WiFi.*`, `Cloud.Config.Set`, `Mqtt.Config.Set`, `Sys.Time.Update`, `Webhook.Create/Update/Delete` | **Denied in v1** | none |

## 5. Network and input safety

| ID | Pri | Requirement |
|---|---|---|
| SEC-040 | M | Device URLs are limited to `http` (and `https` if a device ever supports it), and to private address ranges (RFC 1918, RFC 4193, or an admin-configured CIDR allow-list). Loopback, link-local, the Docker overlay subnets and the metadata address `169.254.169.254` are always blocked. |
| SEC-041 | M | Hostnames are resolved and the resolved IP re-checked against SEC-040 at connect time, to defeat DNS rebinding. |
| SEC-042 | M | All request bodies and query parameters are validated with schemas (Pydantic). Unknown fields are rejected. Time ranges are bounded (for example max 400 days at minute resolution per request). |
| SEC-043 | M | Device responses are treated as untrusted input: schema-validated, size-limited (1 MB per reply) and never rendered as HTML. Device-provided names are escaped in the UI. |
| SEC-044 | M | All SQL through parameterized queries or the ORM. No string-built SQL, including for dynamic circuit formulas. |
| SEC-045 | M | Rate limits: login 5 per minute per IP and account; API 600 requests per minute per session or token; at most 2 concurrent export jobs per user. |
| SEC-050 | M | CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'`. No inline scripts; all assets self-hosted. |
| SEC-051 | M | Error responses never include stack traces, SQL or secrets. Details go to server logs with the request id. |
| SEC-052 | M | Dependency and image scanning (for example `pip-audit`, `npm audit`, Trivy) run in CI. Critical findings block release. |

## 6. Audit log

| ID | Pri | Requirement |
|---|---|---|
| AUD-001 | M | Append-only `audit_log` table: `ts, actor_user_id, actor_token_id, source_ip, action, resource_type, resource_id, site_id, outcome, detail jsonb`. The application database role has insert and select only. |
| AUD-002 | M | Logged actions: login success and failure, logout, MFA changes, user and binding changes, token create and revoke, site/device/circuit changes, device credential set or cleared, every device write command, tariff and assignment changes, bill actuals, exports, settings changes, backups and restores. |
| AUD-003 | M | Secrets are redacted in `detail`. Device password changes log only that a change occurred. |
| AUD-004 | S | Audit log export to CSV for Admin. |

## 7. Data tables

```sql
app_user (id uuid pk, username citext unique, email citext unique null, display_name text,
          password_hash text, mfa_secret_enc bytea null, is_active bool, last_login_at,
          created_at, updated_at)
role (id text pk, name text, builtin bool)                       -- 'admin','site_manager',...
permission (id text pk, description text, global_only bool)
role_permission (role_id text, permission_id text, primary key (role_id, permission_id))
user_role_binding (id uuid pk, user_id uuid, role_id text, site_id uuid null,   -- null = global
                   expires_at timestamptz null, granted_by uuid, created_at)
api_token (id uuid pk, user_id uuid, name text, prefix text, token_hash bytea unique,
           permissions text[], site_id uuid null, kind text,       -- personal, service, kiosk
           expires_at, last_used_at, revoked_at, created_at)
session (id_hash bytea pk, user_id uuid, created_at, last_seen_at, expires_at, ip inet, user_agent text)
audit_log (...)  -- hypertable on ts, see AUD-001
```
