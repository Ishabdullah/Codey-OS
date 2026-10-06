# B2 Census — Private-Codey-Agent (actuator / "hands" limb)

HEAD `efe9a1c` (2026-08-30). Repo: `/data/data/com.termux/files/home/Private-Codey-Agent`.
Cross-checked against Codey-OS main (`/data/data/com.termux/files/home/Codey-OS`), HEAD as of this census (`405d9cf`, 2026-10-06).

Status vocabulary: IMPLEMENTED / PARTIAL / DORMANT / DOCS-ONLY / MISSING.

---

## (a) App architecture + manifest permission inventory

**Entry point:** `lib/main.dart:45` `main()` — inits SharedPreferences, theme, optionally starts
`VoiceAssistantForegroundService` if wake-word config enabled (`lib/main.dart:67-77`), then
`runApp(PrivateAgentApp(...))` (`lib/main.dart:81`). A second entry point `overlayMain()`
(`lib/main.dart:13`) is gated off: `FeatureFlags.floatingOverlayEnabled = false`
(`lib/config/feature_flags.dart:6`) — the only condition that calls `FlutterOverlayWindow.overlayListener.listen` (`lib/main.dart:19`). Floating overlay = DORMANT by explicit flag.

**Screens** (`lib/screens/`): `home_screen.dart` (main chat/task UI), `onboarding_screen.dart`,
`settings_screen.dart`, `task_history_screen.dart`, `business_dashboard_screen.dart` (Codey
integration — see §(d) IMPLEMENTED-but-unreachable finding below).

**Services** (`lib/services/`, 23 files): `ai_service.dart` (LLM calls), `action_handler.dart` +
`task_executor.dart` (parses/executes agent actions), `screen_automation_service.dart`
(accessibility-service UI dump/tap/scroll/type), `communication_service.dart` (SMS/call via
platform intents), `contacts_service.dart`, `app_launcher_service.dart`, `alarm_service.dart`,
`notification_service.dart`, `system_control_service.dart`, `shizuku_service.dart` (privileged
ops via Shizuku), `telegram_service.dart`, `voice_service.dart` / `voice_conversation_controller.dart`
/ `voice_assistant_foreground_service.dart` / `wake_word_settings_service.dart` (voice pipeline),
`chat_history_service.dart`, `task_history_logger.dart`, `skill_memory_service.dart`,
`recovery_engine.dart`, `secure_secret_store.dart` (Keystore-backed secret storage via
`flutter_secure_storage`), and the 3 Codey-specific files in §(b)-(d).

**State management:** no Bloc/Provider/Riverpod — plain `StatefulWidget` + `setState`, plus one
global `ValueNotifier<ThemeMode>` (`lib/main.dart:43`) for theme. Simple, consistent with a
single-screen chat-first app.

**Manifest permissions** (`android/app/src/main/AndroidManifest.xml:5-20`), each matched to the
service that uses it:
| Permission | Used by |
|---|---|
| `INTERNET` | `ai_service.dart` (LLM/API calls), `restoricon_api_client.dart` |
| `RECORD_AUDIO` | `voice_service.dart`, wake-word foreground service |
| `READ_CONTACTS` | `contacts_service.dart` |
| `CALL_PHONE` | `communication_service.dart` (`makeCall`) |
| `SEND_SMS` | `communication_service.dart` (`sendSms`) |
| `READ_PHONE_STATE` | call-state checks in `communication_service.dart` |
| `SET_ALARM` | `alarm_service.dart` |
| `MODIFY_AUDIO_SETTINGS` / `WRITE_SETTINGS` | `system_control_service.dart` |
| `POST_NOTIFICATIONS` | `notification_service.dart` |
| `QUERY_ALL_PACKAGES` | `app_launcher_service.dart`, `third_party_app_automation_service.dart` (package-name lookups) |
| `SYSTEM_ALERT_WINDOW` (`tools:node="remove"`) | explicitly **removed** — overlay feature is flag-gated off, consistent with §(a) above |
| `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MICROPHONE` | `VoiceAssistantForegroundService` |
| `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` | keeps wake-word foreground service alive |
| `BIND_ACCESSIBILITY_SERVICE` (service decl, manifest:166-175) | `AgentAccessibilityService` (native, backs `screen_automation_service.dart`'s UI dump/tap/scroll) |
| `INTERACT_ACROSS_USERS_FULL` (Shizuku provider, manifest:157-163) | `shizuku_service.dart` |
| `BIND_VOICE_INTERACTION` (×2 services, manifest:109-125) | Google Assistant hand-off path (Phase 9, see manifest comment at line 69-83) |

No `READ_SMS`/`RECEIVE_SMS` (app can only send, not read, SMS) and no camera/location permission
— actuation is intentionally narrow: telephony-send, UI-automation, app-launch, device settings.

---

## (b) Endpoint-by-endpoint contract match table — `restoricon_api_client.dart` vs Codey-OS `restoricon_core/api/routes.py`

Default `baseUrl = 'http://127.0.0.1:8765/api/v1'` (`lib/services/restoricon_api_client.dart:14`).
**Codey-OS's actual Core API server defaults to port 8770**, not 8765
(`Codey-OS/utils/config.py:689,707,712` — `get_restoricon_api_config()`). **Port mismatch,
hardcoded, no override point in the app** — nothing in this file or its only caller
(`business_dashboard_screen.dart`) sets `baseUrl` to anything else. At default settings on both
sides, every request from this client 404s/connection-refuses against the real Core API.

| App method | HTTP call | Codey-OS route | Match? |
|---|---|---|---|
| `getExecutiveReport()` (`restoricon_api_client.dart:26-28`) | `GET /reports/executive` | `GET /api/v1/reports/executive` exists, aliased with `/reports/summary` (`routes.py:4407-4411`, calls `AnalyticsSearchService.get_executive_dashboard`) | Path/shape MATCH, but see auth gate below |
| `getFinancialSummary()` (`:31-33`) | `GET /finance/summary` | `GET /api/v1/finance/summary` exists (`routes.py:4009-4013`, `FinanceService.get_financial_summary`) | Path MATCH; **field-name MISMATCH** — see below |
| `getArAging()` (`:36-38`) | `GET /finance/ar-aging` | `GET /api/v1/finance/ar-aging` exists (`routes.py:4005-4007`) | MATCH, but **never called** — see §(i) DORMANT |
| `getAppointments({limit})` (`:41-59`) | `GET /appointments?limit=N` | `GET /api/v1/appointments` exists, honors `limit` (`routes.py:3153-3166`, `scheduling.list_appointments`) returns `{"appointments": [...]}` | Shape MATCH (`appt.to_dict()` list under `appointments` key, as the Dart code expects at `restoricon_api_client.dart:49`) |
| `getProjects({status, limit})` (`:62-80`) | `GET /projects?status=X&limit=N` | `GET /api/v1/projects` exists but `CRMService.list_projects(actor, customer_id=None, property_id=None)` (`crm_service.py:2898-2900`) **takes no `status` or `limit` parameter** | **Param MISMATCH** — `status`/`limit` query params are silently ignored server-side; the client always gets the full unfiltered project list regardless of the `status='active'` default it requests |
| `getCustomers({limit})` (`:83-101`) | `GET /customers?limit=N` | `GET /api/v1/customers` exists (`routes.py:1256`) | Path exists, response shape not verified further — **method is never called anywhere in the app** (see §(i) DORMANT) |

**Field-name mismatch detail (`getFinancialSummary`):** `FinanceService.get_financial_summary()`
(`restoricon_core/services/finance_service.py:663-693`) returns `total_revenue`, `total_expenses`,
`net_profit`, **`net_margin_percent`** (line 687), `total_ar_outstanding`, `ar_buckets` — there is
**no `gross_margin_percent` key** in this payload. `business_dashboard_screen.dart:111` reads
`_financials['gross_margin_percent'] ?? _kpiReport['financial']?['gross_margin_percent'] ?? 0.0`.
The primary source (`_financials`, from `/finance/summary`) will always be `null` for this field;
the UI is saved only by the fallback to `_kpiReport['financial']['gross_margin_percent']`, which
**does** exist (`AnalyticsSearchService.get_executive_dashboard`,
`analytics_search_service.py:484-488`, returns a `"financial"` block with `gross_margin_percent`
at line 488). Net effect: the margin figure displayed is silently sourced from the wrong endpoint
(executive report, not finance summary) due to this drift; it happens to still render a number.

**Auth-gate risk on `/reports/executive`:** `AnalyticsSearchService.get_executive_dashboard`
requires **both** `PERM_VIEW_REPORTS` **and** `PERM_READ_TEAM_SALES_DATA`
(`analytics_search_service.py:347`, a NEW-550 fix noted in-code). Whatever token/role this app
authenticates as must hold both permissions or `getExecutiveReport()` gets a 403 and the dashboard
silently falls back to its cached/empty map (`restoricon_api_client.dart:115-120`) with no visible
error distinct from "server unreachable."

**Verdict: PARTIAL at best, and unreachable in practice** — even setting aside the port mismatch
(which alone is fatal at defaults), the client cannot be exercised at all because its only caller
(`BusinessDashboardScreen`) is never constructed with a working `apiClient` (see §(d)/(i)).

---

## (c) Device bridge protocol analysis — `device_bridge_client_service.dart` vs Codey-OS `ccos/core/device_bridge.py`

**App side (`lib/services/device_bridge_client_service.dart`):** acts as a **TCP client**
(`Socket.connect(host, port)`, default `host='127.0.0.1'`, `port=8088`,
`device_bridge_client_service.dart:24-25,42`), auto-reconnects every 5s on disconnect
(`:63-71`), speaks **line-delimited JSON envelopes** (`\n`-terminated, `:83-105`). Envelope shape:
`{request_id, status, data, error}` out, `{request_id, action_type, payload, auth_token}` in
(`:108-230`). Action types handled: `inspect_ui`, `perform_gesture`, `send_sms`, `make_call`,
`launch_app`, `third_party_message`, `execute_task` (`:127-213`).

**Codey-OS side (`ccos/core/device_bridge.py`):** defines the *mirror-image* vocabulary —
`DeviceBridgeRequest`/`DeviceBridgeResponse` envelopes (`device_bridge.py:103-173`) with the
**same action-type set** plus `read_notifications` (`:20-28`), and a `DeviceBridgeServer` that can
either bind a real loopback TCP socket (`:195-326`) or dispatch in-process. **The envelope schema
and action-type vocabulary match well** — this part of the contract is genuinely aligned (unusual
for a 5-week-stale pairing, and worth preserving if either side is revised).

**Where it breaks: nobody is actually listening, and the roles are backwards from what the app
expects.**
- The app's `DeviceBridgeClientService` connects **out** to `127.0.0.1:8088` expecting something
  to be listening there.
- `DeviceBridgeServer.__init__` defaults to `port=0` (ephemeral) (`device_bridge.py:191`); no
  code anywhere in Codey-OS passes `port=8088` or any other fixed port to it.
- `DeviceBridgeServer.start()` (the only method that actually opens a socket,
  `device_bridge.py:308-326`) is called in exactly one place in the whole Codey-OS tree:
  `ccos/tests/test_device_bridge.py:144-145`, with `port=0`. It is **never called from any
  production entry point** (`main.py`, `core/daemon.py`, or any plugin `install()`/lifecycle
  hook) — confirmed by grepping every `.start()` call site in the repo.
- The capability actually exposed to CCOS's planner/orchestrator
  (`ccos/plugins/device/bridge/bridge.py:14-19`, `_get_client()`) calls
  `get_default_device_bridge_client()`, which is `DeviceBridgeClient(server_instance=
  get_default_device_bridge_server())` (`device_bridge.py:572-573`) — the **in-process
  direct-dispatch branch** (`device_bridge.py:398-405`: `if self.server_instance is not None or
  self.port is None: ... server.handle_envelope(req_dict)` — no socket I/O at all).
- `DeviceBridgeServer._register_default_handlers()` (`device_bridge.py:217-266`) wires every
  action type to a **hardcoded mock**: `inspect_ui` returns a fake `{"root": {"class":
  "FrameLayout", "children": []}}` tree and fixed `1080x2400` screen size; `send_sms`/`make_call`
  return `{"sent": True, ...}` / `{"initiated": True, ...}` without touching any transport at all.

**Verdict: DOCS-ONLY / mock.** The protocol design is sound and the two sides agree on wire format,
but there is no real socket pairing in either codebase today — CCOS's "device bridge" capability
currently fabricates every result. This is a different, more serious finding than a port
mismatch: even if the port were fixed to agree, there is no production code path that would ever
open 8088 (or any port) to let the Flutter app's socket connect to anything real.

A second, separate port number (8766) appears in `ccos/plugins/device/private_agent/manifest.json`
(`"health_endpoint": "http://127.0.0.1:8766/health"`, `"start_command": ["python3", "agent.py"]`) —
a *third* unrelated port/protocol guess for the same conceptual link, for a plugin whose
`start_command` (`python3 agent.py` inside that plugin's own directory) **does not exist**
(confirmed: no `agent.py` under `ccos/plugins/device/private_agent/`; the only `agent.py` in the
repo is `core/agent.py`, the unrelated coding-agent main loop). A stale `private_agent.pid`
(content: `22834`) sits in that directory from some earlier manual run, is not from this plugin's
own process, and the plugin is not registered in any `ccos/data/*.json` capability listing
(grep for `private_agent`/`device_secure_relay` across `ccos/data/*.json` returns nothing).
**This third integration point is pure DOCS-ONLY fiction** — a manifest describing a process and
HTTP surface that has never existed.

---

## (d) Third-party automation capability analysis — `third_party_app_automation_service.dart`

Supports `whatsapp`, `messenger`, `sms`, `instagram`, `telegram`, `other`
(`ThirdPartyApp` enum, `:7-14`). Dispatch (`sendMessage()`, `:66-96`):
- **WhatsApp** (`:99-131`): launches `whatsapp://send?phone=...&text=...` via
  `url_launcher` (an Android Intent, not the WhatsApp Business API), then — if
  `useAccessibilityFallback` (default `true`) — waits 1200ms and calls
  `_screenService.clickByText('Send')` (`:112-113`), i.e. **drives the Accessibility Service to
  tap WhatsApp's own Send button** to actually deliver the message the intent only pre-filled.
- **SMS** (`:134-163`): `sms:` URI intent with `body` query param — opens the native Messages app
  pre-filled; does **not** auto-tap send (no accessibility fallback here), so SMS send is
  pre-filled-only pending user confirmation on the native composer, unlike WhatsApp's path.
- **Messenger / Instagram / Telegram / other** (`:166-199`): opens the target package
  (`_screenService.openApp(pkg)`), waits 1500ms, then if a `TaskExecutor` is supplied, hands off a
  free-text goal like `'In $app, search for contact "$recipient", open chat, type message:
  "$message", and click send.'` (`:179`) to multi-step accessibility automation
  (`TaskExecutor.executeTask`); if no executor, it only reports `'Dispatched via application
  launch'` without ever actually composing/sending anything (`:191-198`) — i.e. for these four
  channels, actual delivery depends entirely on whether a `TaskExecutor` instance was passed in.
- Accessibility capability used throughout is `ScreenAutomationService` (not read in detail here,
  out of this census's required-file list, but its methods — `dumpScreen`, `clickByText`,
  `clickAt`, `scroll`, `typeText`, `openApp` — are the ones backing `AgentAccessibilityService` in
  the manifest).

**What it can actually do to other apps:** read their on-screen UI tree (via accessibility dump),
tap/scroll/type into them, and launch them by package name — i.e. full UI automation surface over
any app the Accessibility Service can see, gated only by `QUERY_ALL_PACKAGES` +
`BIND_ACCESSIBILITY_SERVICE`, with no allow-list of target packages in this file.

---

## (e) Auth flow + credential flags

**No login/token-acquisition flow exists in this app.** `RestoriconApiClient.authToken` is a
plain nullable constructor parameter (`restoricon_api_client.dart:7,15`) set once, never refreshed,
with no code anywhere in the app that calls an endpoint to obtain one (no `/api/v1/auth/login` call
site in this repo — that route only exists server-side, `Codey-OS/restoricon_core/api/routes.py:850`).
`DeviceBridgeClientService.authToken` (`device_bridge_client_service.dart:12,26`) is the same
pattern — accepted but never populated by any caller.

Since `RestoriconApiClient` is **never instantiated anywhere in the app** (see §(i) below —
its only consumer, `BusinessDashboardScreen`, is constructed with zero arguments at both call
sites), the auth token is never set in practice; every request this client would send carries no
`Authorization` header at all (`_headers` getter at `:19-23` omits it when `authToken` is
null/empty).

**No hardcoded credential found.** Grepped `lib/` for Bearer-token literals, inline `api_key =`/
`secret =` assignments — zero hits. Secrets that do exist in the app (bot tokens, etc., used by
`telegram_service.dart`) go through `SecureSecretStore` (`lib/services/secure_secret_store.dart`),
which is Keystore-backed (`flutter_secure_storage`) with a one-time plaintext-SharedPreferences
migration path (`:10-29`) — appropriate pattern, nothing flagged here.

**No flag to raise:** there is no committed credential in this repo's tracked files for the
Codey-OS integration surface. The real finding is the *absence* of any auth flow, not a leak.

---

## (f) Unfinished / missing actuator work inventory

1. **Build-breaking constructor mismatch** — `BusinessDashboardScreen` requires `apiClient`
   (`business_dashboard_screen.dart:6,9-13`, no default) but both navigation call sites construct
   it with zero arguments: `lib/screens/home_screen.dart:637` and `lib/screens/home_screen.dart:1054`
   (`const BusinessDashboardScreen()`). This is a Dart compile error — a required named parameter
   with no value supplied. **This is new evidence beyond what the directive already established**
   about the repo being "known not fully integrated" — it means the dashboard wiring commit
   (`efe9a1c`, the most recent of the three Codey-integration commits, explicitly titled
   "wire Business Dashboard into AppBar and drawer navigation") does not actually compile as
   committed. CI (`android-release.yml`) runs `flutter build apk --release` on every push to
   `main`/tag — if that workflow has run since `efe9a1c` landed, it should be failing red; this
   census did not run the build (static inspection only, per instructions) so this is reported as
   a static-analysis finding, not a confirmed CI failure. **Flag for NEW_ISSUES.md: Confirmed
   (static) / needs a CI-log check to confirm red-build in practice.**
2. **No instantiation site for `RestoriconApiClient` or `DeviceBridgeClientService` anywhere in
   the app** outside their own files and the broken `BusinessDashboardScreen` — no `main.dart`
   bootstrap, no settings-screen config UI to enter a base URL/token/host/port. The entire
   Codey-OS integration surface has no user-facing configuration path at all.
3. **`DeviceBridgeClientService.connect()` is never called** anywhere in the app — confirmed by
   grep for call sites outside its own definition file. Nothing ever opens the socket client-side
   either, compounding the server-side absence in §(c).
4. **No test coverage for any of the 4 Codey-integration files** — `test/` has 10 files
   (`action_handler_test.dart`, `ai_service_test.dart`, `ai_service_parse_action_test.dart`,
   `screen_automation_service_test.dart`, `task_executor_test.dart`, `task_json_utils_test.dart`,
   `tts_settings_service_test.dart`, `voice_conversation_controller_test.dart`,
   `voice_service_test.dart`, `wake_word_settings_service_test.dart`) — none for
   `restoricon_api_client.dart`, `device_bridge_client_service.dart`,
   `third_party_app_automation_service.dart`, or `business_dashboard_screen.dart`.
5. **`getCustomers()` and `getArAging()`** on `RestoriconApiClient` are defined but have zero
   callers anywhere in `lib/` (confirmed by grep) — dead client methods for endpoints the
   dashboard screen doesn't use.
6. **Server-side `/api/v1/projects` ignores the `status`/`limit` filters** the client sends
   (§(b)) — not something the app can fix; flagged for the Codey-OS side.
7. **Device bridge has no real transport** (§(c)) — `DeviceBridgeServer.start()` is dead code in
   production; the CCOS capability that's supposed to back it fabricates all results.
8. **`private_agent` plugin manifest describes a nonexistent process** (§(c)) — `python3 agent.py`
   with no such file, a third port (8766), not registered in any capability listing.

---

## (g) Irreversible-action inventory + current gating

Actions this app can perform that are irreversible once executed, and what — if anything — confirms
them before execution:

| Action | File:line | Gated/confirmed? |
|---|---|---|
| Send SMS | `communication_service.dart` via `sendSms()`, invoked from `device_bridge_client_service.dart:158-163` (`send_sms` action) and from task/action-handler flows | **No confirmation dialog found in the 4 files read for this census.** The device-bridge path dispatches directly on receiving a socket request with no human-in-the-loop step in this file. (Codey-OS's own mock `DeviceBridgeServer` and the real `communication_service.dart` path are the only two callers that matter; neither pauses for confirmation at this layer.) |
| Make phone call | `communication_service.dart` via `makeCall()`, invoked from `device_bridge_client_service.dart:165-169` (`make_call` action) | Same — no confirmation layer in these files. Note Codey-OS's `ccos/core/device_bridge.py:277-299` (`validate_telephony_safety`) **does** block emergency numbers (911/112/999/etc.) server-side, but that veto only runs on the CCOS mock-dispatch path (§(c)), not when the *Flutter app's own* `handleRequestEnvelope` (`device_bridge_client_service.dart:108-230`) processes a `make_call`/`send_sms` request directly — **the Dart-side handler has no equivalent emergency-number veto at all**. This is a real asymmetry: the safety veto exists only on the side that currently does nothing real, not on the side that would actually dial/text. |
| Send WhatsApp message (with accessibility auto-tap Send) | `third_party_app_automation_service.dart:99-131` | No confirmation — launches intent and auto-taps Send after 1200ms if `useAccessibilityFallback` (default `true`). This is the one channel in this service that is auto-confirmed by code, not by the user. |
| Send Messenger/Instagram/Telegram message via `TaskExecutor` | `third_party_app_automation_service.dart:166-199` | No confirmation visible in this file; delegates to `TaskExecutor.executeTask` with a free-text goal, autonomy level not verified here (out of the 4-file scope). |
| UI automation (`perform_gesture`, arbitrary tap/scroll/type on any foreground app) | `device_bridge_client_service.dart:136-156` | No allow-list or confirmation — any `perform_gesture` request executes immediately against whatever app is in focus. |
| `execute_task` (multi-step accessibility automation toward a free-text goal) | `device_bridge_client_service.dart:188-205` | No step-count cap enforced in this file beyond whatever `TaskExecutor` itself does (not read); no human checkpoint visible here. |

**Net assessment for the Action Gateway / human-authorization plan:** as currently written, this
app acts directly on every irreversible action type with no built-in confirmation step of its own
for the device-bridge dispatch path — any gating that exists today lives only in the mostly-mock
Codey-OS `device_bridge.py` emergency-number veto, which (per §(c)) isn't wired to anything real.
If/when the transport gap is closed, a human-authorization layer needs to be added either in this
app's `handleRequestEnvelope` or as a gate Codey-OS enforces *before* ever reaching a real socket —
neither exists today.

---

## (h) Build / test / CI state

- **Tests:** `test/` has 10 unit-test files (listed in §(f) item 4) plus the two bundled local
  plugins' own smoke tests (`local_plugins/agent_native`, `local_plugins/flutter_overlay_window`).
  None cover the 4 Codey-integration files.
- **CI:** `.github/workflows/android-release.yml` — triggers on push to `main` and on `v*` tags
  (`:3-8`). Steps: `flutter pub get` → `flutter analyze --no-fatal-infos --no-fatal-warnings || true`
  (analyzer failures are **swallowed**, `:40-42`, comment flags this as a deliberate "P5-3 audit
  fix") → `flutter test` → `flutter build apk --release` (full and `--split-per-abi`) → GitHub
  Release publish. **The `flutter build apk --release` step is not soft-failed** — if the
  constructor-mismatch bug in §(f) item 1 is real (it is, per static read), this step should fail
  on every push since `efe9a1c`. This census did not check actual run history (no network/build
  execution per instructions) — flagging as a question for Ish/the live-verifier in §(j).
- **Build config:** `pubspec.yaml` — `environment.sdk: ^3.10.3`, Flutter via `sdk: flutter` (no
  pinned Flutter version beyond `channel: stable` in CI). Dependency list (`pubspec.yaml:9-40`,
  partially shown) is current-looking (http ^1.4.0, speech_to_text ^7.0.0, flutter_secure_storage
  ^11.0.0, permission_handler ^11.4.0) — no obviously stale/abandoned packages spotted in the
  portion read. Not re-verified against `pub.dev` latest (would require network; out of scope for
  static inspection).
- **Gradle/Android SDK versions:** not inspected in this pass (would require reading
  `android/app/build.gradle(.kts)` and `android/build.gradle(.kts)`, not in the 4 required files or
  manifest) — flagged as unexamined in §(j).

---

## (i) DORMANT findings (reachability explicitly checked)

Search method for each: `grep -rn` for the symbol/class name across `lib/` outside its own
definition file, using the full-path grep binary per environment notes.

- **`BusinessDashboardScreen`** — reachable via navigation (`home_screen.dart:637,1054`), but
  construction is broken (§(f) item 1) — effectively DORMANT-by-compile-failure despite being
  "wired" in the navigation sense the directive/commit message claims.
- **`RestoriconApiClient`** — zero instantiation sites in the app; only referenced inside its own
  file and inside the broken `BusinessDashboardScreen`'s required-parameter declaration. DORMANT.
- **`DeviceBridgeClientService`** — zero instantiation or `.connect()` call sites anywhere in
  `lib/` outside its own file. DORMANT.
- **`getCustomers()`, `getArAging()`** (`RestoriconApiClient` methods) — defined, zero callers.
  DORMANT.
- **`floatingOverlayMain()` / overlay listener path** (`main.dart:13-24`) — gated by
  `FeatureFlags.floatingOverlayEnabled = false` (`feature_flags.dart:6`), explicitly disabled by a
  code comment ("Temporarily disabled while the floating-window implementation is being
  stabilized"). DORMANT by design, not a bug — included for completeness since it also touches the
  overlay permission removal in the manifest.
- **Codey-OS side:** `ccos/core/device_bridge.py`'s `DeviceBridgeServer.start()` (real socket) —
  called only from one test file with an ephemeral port; no production call site. DORMANT.
  `ccos/plugins/device/private_agent/` — manifest describes a process/HTTP surface
  (`python3 agent.py`, port 8766) that has no backing file and isn't registered in any
  `ccos/data/*.json` capability listing. DOCS-ONLY (never was live, not merely dormant).

---

## (j) Open questions

1. Has `android-release.yml`'s `flutter build apk --release` step actually been failing since
   `efe9a1c`? This census is static-only; a live-verifier or a check of GitHub Actions run history
   for this repo would confirm or rule out the compile-break claim in §(f) item 1.
2. What permission set does whatever token eventually gets issued to this app need, given
   `/api/v1/reports/executive` requires **both** `PERM_VIEW_REPORTS` and
   `PERM_READ_TEAM_SALES_DATA` (§(b))? Is there a designed "device/limb" role in the 96-row
   `api_tokens` table, or would this app authenticate as a named human user?
3. Which side is supposed to be the TCP *server* for the device bridge — Codey-OS (listening for
   the Android app to connect, matching the app's current client-only code) or the Android app
   (with Codey-OS's `DeviceBridgeClient` meant to dial out to it, matching the *naming* of the
   Codey-OS classes but not their current in-process-only default wiring)? The two sides' class
   names (`DeviceBridgeClientService` in the app, `DeviceBridgeClient`/`DeviceBridgeServer` in
   Codey-OS) suggest the designers intended Codey-OS to run the server and the app to dial in — but
   no code anywhere starts that server with a real, fixed port.
4. Is the `private_agent` plugin manifest (8766, `python3 agent.py`) a leftover/abandoned design
   sketch, or was a real companion process planned that was never committed? Worth a direct
   question to Ish rather than more code archaeology.
5. Gradle/Android SDK/`minSdkVersion`/`targetSdkVersion` were not inspected this round (outside the
   4 required files and manifest) — needed for a full build-currency assessment per task item 6.
