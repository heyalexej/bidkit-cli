# Authentication & configuration

`bidkit` reuses the SDK's OAuth flows and the **bidkit-cli** JSON config format. There is
one credentials file; the CLI adds no second format.

## Config file

Default: `~/.config/bidkit/config.json` (a legacy `~/.config/ebay-cli/config.json` is read
as a fallback when the default is absent). Override with `--config PATH`.

```json
{
  "environment": "production",
  "marketplace_default": "EBAY_DE",
  "credentials": {
    "app_id": "...-PRD-...",
    "cert_id": "...",
    "ru_name": "...",
    "refresh_token": "...",
    "granted_scopes": "https://api.ebay.com/oauth/api_scope/sell.inventory ..."
  }
}
```

A sibling `signing-key.json` is auto-detected for Finances/refund signing.

## Precedence (highest first)

1. CLI flags (`--environment`, `--marketplace`, `--timeout`, `--max-retries`)
2. `EBAY_*` environment variables
3. the `--config` file
4. bidkit defaults

Useful env vars: `EBAY_APP_ID`, `EBAY_CERT_ID`, `EBAY_RU_NAME`, `EBAY_REFRESH_TOKEN`,
`EBAY_SANDBOX`, `EBAY_MARKETPLACE_ID`, `EBAY_SCOPES`, `EBAY_BASE_URL`.

## Commands

```bash
bidkit auth doctor               # read-only diagnostic (never hits the network)
bidkit auth doctor --check-network    # verify the app keyset (client_credentials grant)
bidkit auth doctor --check-user-token # verify the configured refresh token (read-only)
bidkit auth scopes               # show configured (and per-operation) scopes
bidkit auth scopes --operation sell_inventory.getInventoryItems
bidkit auth login                # authorization-code flow; mints a refresh token
bidkit auth login --no-browser --write-config
bidkit auth cache path           # token cache location
bidkit auth cache clear --yes    # clear the cache (destructive; needs --yes)
```

`--check-network` proves the application keyset can mint a **client** token; it
does not prove the seller/user refresh token is usable. Use `--check-user-token`
to refresh the configured token read-only and validate seller consent/scopes.
Neither check mutates account state, and no token value is ever printed.

## Sandbox vs production

eBay App IDs encode the environment: `...-PRD-...` (production) or `...-SBX-...` (sandbox).
`auth doctor` and `auth login` detect a keyset/environment mismatch and refuse before any
browser opens or network call.

## What is never printed

Access tokens, refresh tokens, client secrets, signing private keys, and `Authorization`
headers are redacted in `auth doctor`, `config show`, errors, debug logs, and `--dry-run`.
