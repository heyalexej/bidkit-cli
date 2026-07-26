# Configuration

The CLI is a thin shell over `bidkit.EbayConfig`. One config file, used by both the SDK and CLI.

## Precedence (highest first)

1. Command-line flags: `--config`, `--environment`, `--marketplace`, `--timeout`, `--max-retries`.
2. `EBAY_*` environment variables.
3. The `--config` file (ebay-cli JSON format).
4. bidkit defaults.

## Inspect the effective config

```bash
bidkit config show        # resolved, non-secret values + api_root + token cache path
```

## Environment override

```bash
bidkit --environment sandbox api list
bidkit --marketplace EBAY_US sell inventory get-inventory-items
```

`--environment sandbox` sets `sandbox=true` on the resolved config (it does not edit the file).

## Config file fields

| ebay-cli field            | EbayConfig field      |
|---------------------------|-----------------------|
| `credentials.app_id`      | `app_id`              |
| `credentials.cert_id`     | `cert_id`             |
| `credentials.ru_name`     | `ru_name`             |
| `credentials.refresh_token` | `refresh_token`     |
| `credentials.granted_scopes` | `scopes`            |
| `environment`             | `sandbox` (== "sandbox") |
| `marketplace_default`     | `marketplace_id`      |

See `references/authentication.md` for the token cache and signing key.
