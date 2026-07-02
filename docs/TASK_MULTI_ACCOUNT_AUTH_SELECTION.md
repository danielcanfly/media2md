# Task: Multi-Account Auth Selection

## Summary

Media2MD currently binds authentication at the browser-profile level for
YouTube, Instagram, and TikTok.

That is not sufficient for real-world usage when one browser profile contains
multiple signed-in platform accounts.

The target outcome of this task is to make Media2MD account-aware instead of
profile-only:

- discover candidate platform accounts inside a chosen browser profile
- show account identity clearly to the user
- let the user explicitly select which account Media2MD should use
- persist that choice
- verify and report the selected account identity truthfully

This task should start with Instagram, then extend the contract to YouTube and
TikTok where technically feasible.

## Problem

Today the auth model is roughly:

```text
provider -> browser -> profile
```

But the real user need is:

```text
provider -> browser -> profile -> account
```

Without explicit account selection, Media2MD can:

- read a valid cookie snapshot from the chosen browser profile
- authenticate successfully
- still bind to the wrong account

Example failure mode:

- Chrome frontmost session appears to be Instagram account A
- Media2MD exports valid Instagram cookies from the same profile
- those cookies actually authenticate as account B
- `auth disconnect` removes Media2MD's local binding, but does not remove the
  browser's underlying cookies
- reconnecting to the same profile still resolves to account B

This is confusing, hard to debug, and not production-level UX.

## Goals

1. Let users see which account Media2MD is actually binding to.
2. Let users explicitly choose the account when multiple accounts are present.
3. Persist the chosen account identity in Media2MD config.
4. Make `auth verify` report the resolved account identity.
5. Warn when the selected identity and resolved live identity do not match.
6. Make account switching predictable across supported providers.
7. Keep `disconnect` semantics truthful: disconnect Media2MD, not the browser.

## Non-Goals

1. Do not automate password entry.
2. Do not bypass 2FA, CAPTCHA, or platform challenges.
3. Do not try to control a provider's native multi-account UI in the browser.
4. Do not promise equal multi-account depth across all providers in the first
   release.
5. Do not change public creator/media processing behavior until auth identity is
   trustworthy.

## User Experience Principles

1. The system must never silently choose a different account than the one shown
   to the user.
2. If the system cannot distinguish accounts reliably, it must say so.
3. Browser profile selection and account selection must be separate steps.
4. Verification output must include account identity whenever possible.
5. Error messages must explain whether the problem is:
   - no browser profile selected
   - no cookies found
   - multiple candidate accounts detected
   - selected account no longer matches live session
   - provider challenge or logged-out session

## Current State

Current public auth surface:

```text
media2md auth profiles
media2md auth connect
media2md auth verify
media2md auth refresh
media2md auth status
media2md auth logout
media2md auth disconnect
```

Current behavior:

- YouTube / Instagram / TikTok support browser-profile based connection
- Bilibili does not use the same auth flow today
- `connect` stores browser/profile and exports a cookie snapshot
- `verify` checks whether the session is authenticated
- `disconnect` removes Media2MD's local binding and snapshot file
- `disconnect` does not log the browser out

Current gap:

- no account discovery
- no account selection
- no persisted selected account identity
- no mismatch detection between intended and resolved account

## Proposed Public Surface

### New commands

```text
media2md auth accounts <provider> --browser <browser> --profile <profile>
media2md auth select <provider> --browser <browser> --profile <profile> --account <account-key>
```

Alternative if we want to minimize command sprawl:

```text
media2md auth connect <provider> --browser <browser> --profile <profile> --account <account-key>
```

Recommended first version:

1. keep `auth connect`
2. add `auth accounts`
3. add `--account` to `auth connect`
4. keep `auth select` optional for later

This gives a simple operator flow:

```bash
media2md auth profiles instagram --browser chrome
media2md auth accounts instagram --browser chrome --profile Default
media2md auth connect instagram --browser chrome --profile Default --account <account-key>
media2md auth verify instagram
```

## Proposed Operator Flows

### Flow A: single account detected

```bash
media2md auth profiles instagram --browser chrome
media2md auth accounts instagram --browser chrome --profile Default
```

If exactly one valid account is detected:

- show it clearly
- allow `auth connect` without `--account`
- persist that identity

### Flow B: multiple accounts detected

```bash
media2md auth accounts instagram --browser chrome --profile Default
```

Output should list:

- stable account key
- username / handle
- account id if known
- display name if known
- authenticated / stale / unknown status

Then require:

```bash
media2md auth connect instagram --browser chrome --profile Default --account <account-key>
```

### Flow C: verify later

```bash
media2md auth verify instagram
```

Verification should report:

- selected account key
- selected username
- resolved live username
- resolved live user id
- match status
- mismatch warning if different

### Flow D: disconnect

```bash
media2md auth disconnect instagram --yes
```

Should explicitly state:

- Media2MD binding removed
- browser session unchanged
- selected account cleared

## Provider Rollout Strategy

### Phase 1: Instagram

Instagram should be first because:

- multi-account usage is common
- the current confusion has already been observed
- the UX gap is highest here
- account identity is important for creator workflows

### Phase 2: TikTok

TikTok should be second if account identity can be resolved reliably from
session cookies plus a lightweight authenticated endpoint.

### Phase 3: YouTube

YouTube likely needs a more careful design because Google account and YouTube
channel identity are not always a one-to-one mapping.

Possible outcomes:

- Google account identity only
- channel identity when available
- explicit warning when multiple channels or ambiguous channel context exist

### Phase 4: Bilibili

Only after Bilibili auth contract itself is more fully defined.

## Technical Design Direction

## 1. Persist selected identity

Extend saved provider auth metadata with fields like:

```json
{
  "selected_account_key": "...",
  "selected_account_username": "...",
  "selected_account_id": "...",
  "selected_account_display_name": "...",
  "account_selection_required": false,
  "last_resolved_account_key": "...",
  "last_resolved_account_username": "...",
  "last_resolved_account_id": "...",
  "last_account_match": true
}
```

## 2. Discovery layer

Add a provider-specific account discovery layer.

Desired output shape:

```json
{
  "provider": "instagram",
  "browser": "chrome",
  "profile": "Default",
  "accounts": [
    {
      "account_key": "...",
      "username": "...",
      "account_id": "...",
      "display_name": "...",
      "status": "authenticated"
    }
  ]
}
```

## 3. Verify layer

Verification should not only answer "authenticated?".
It should also answer "authenticated as whom?".

Desired verify payload additions:

```json
{
  "selected_account_key": "...",
  "selected_account_username": "...",
  "resolved_account_key": "...",
  "resolved_account_username": "...",
  "resolved_account_id": "...",
  "account_match": true,
  "account_mismatch_warning": null
}
```

## 4. Mismatch handling

If the selected account and resolved account differ:

- auth state should remain truthful
- the system should not silently auto-correct
- return a warning and an explicit remediation path

Example remediation:

- disconnect and reconnect with the intended account
- use a dedicated browser profile for each platform account

## Platform Feasibility Notes

### Instagram

Best first target.

Possible strategy:

- export cookies from selected browser profile
- probe an authenticated Instagram endpoint that returns account identity
- derive username and id from the response
- if multiple active sessions exist, investigate whether they can be enumerated
  from cookies alone or whether additional browser-state inspection is needed

Important caveat:

- there may be cases where the browser UI presents account A but the exported
  effective session cookie authenticates as account B
- the system must report the effective session truthfully even if enumeration is
  incomplete

### TikTok

Possible strategy:

- authenticated probe endpoint
- derive handle/user id from the effective session

Risk:

- account enumeration may be more limited than effective-session detection

### YouTube

Possible strategy:

- detect Google login state from cookies
- attempt to resolve effective YouTube identity separately

Risk:

- Google account identity and YouTube channel identity may diverge
- multi-channel contexts may require a more limited first release

## Recommended Delivery Plan

### Batch A: Instagram identity truthfulness

Goal:

- `auth verify instagram` reports resolved username and id
- `disconnect` messaging is clarified
- README and docs explain dedicated profile best practice

This batch does not yet require account enumeration.
It closes the worst "I thought I was A but it was really B" blind spot.

### Batch B: Instagram account discovery

Goal:

- add `auth accounts instagram --browser ... --profile ...`
- return candidate account list where technically possible
- persist account metadata in auth config

### Batch C: Instagram account selection

Goal:

- add `--account` support to `auth connect instagram`
- require explicit account choice when multiple candidates are available
- surface mismatch warnings in `auth verify instagram`

### Batch D: shared auth account contract

Goal:

- define shared schema and CLI behavior
- extend the contract to TikTok
- evaluate YouTube separately with realistic scope

## Documentation Changes Needed

Update:

- README
- FIRST_RUN.md
- CLI_REFERENCE.md
- AGENT_INSTALL.md
- AGENT_OPERATIONS.md
- AGENT_DECISION_MAP.md

Required wording changes:

1. `disconnect` does not log the browser out
2. a dedicated browser profile is strongly recommended
3. do not rely on the main day-to-day account when avoidable
4. browser profile selection is not the same as account selection

## Test Plan

### Unit tests

1. account discovery payload shape
2. account selection persistence
3. verify payload includes resolved identity
4. mismatch warning behavior
5. disconnect clears selected identity

### Regression tests

1. single-account happy path still works
2. profile-only flows still work when only one account exists
3. reconnecting after disconnect does not claim browser logout
4. multi-account ambiguity is surfaced explicitly

### Live tests

#### Instagram

1. one dedicated profile, one account
2. one profile with multiple Instagram accounts
3. frontmost account differs from effective session account
4. expired session
5. challenge/login-required state

#### TikTok

1. one account dedicated profile
2. verify identity reporting

#### YouTube

1. verify Google sign-in truthfulness
2. evaluate whether reliable channel/account selection is feasible

## Acceptance Criteria

### Minimum acceptable first release

1. `auth verify instagram` reports which account Media2MD actually resolved
2. `auth disconnect` clearly says it did not log the browser out
3. docs recommend dedicated browser profiles
4. a mismatch between selected and resolved Instagram account is visible to the
   user

### Stronger release

1. `auth accounts instagram --browser ... --profile ...` lists candidate
   accounts
2. `auth connect instagram --account ...` persists an explicit account choice
3. account choice survives refresh and verify
4. mismatch warnings are machine-readable and human-readable

### Full target state

1. shared multi-account auth contract exists
2. Instagram complete
3. TikTok partially or fully aligned
4. YouTube aligned as far as channel/account semantics allow

## Recommendation

The right next step is:

1. implement Instagram identity truthfulness first
2. then add Instagram account discovery and selection
3. only then generalize the contract to other providers

This keeps the first fix grounded in the real bug the user already hit, instead
of overdesigning a cross-provider abstraction before the hardest user-facing
failure is solved.
