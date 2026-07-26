# Account v2 API

- **Service key:** `sell_account_v2`
- **CLI:** `bidkit sell account-v2`
- **Version:** 2.2.0
- **Base path:** `/sell/account/v2`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_account_v2_oas3.json`
- **Operations:** 14

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_account_v2.OPERATION_ID
bidkit api schema sell_account_v2.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_account_v2.createCalculatedShippingRules` | POST | `/combined_shipping_rules/create_calculated_shipping_rules` | unknown | Creates calculated shipping rules that determine combined shipping costs based on item att |
| `sell_account_v2.createFlatShippingRules` | POST | `/combined_shipping_rules/create_flat_shipping_rules` | unknown | Creates flat-rate rules that apply standard combined shipping costs for a seller's listing |
| `sell_account_v2.createPromotionalShippingRule` | POST | `/combined_shipping_rules/create_promotional_shipping_rule` | unknown | Creates promotional shipping rules, such as discounts or free-shipping thresholds. |
| `sell_account_v2.getCombinedShippingRules` | GET | `/combined_shipping_rules` | read | Retrieves all combined shipping rule configurations defined for the seller. |
| `sell_account_v2.getPayoutSettings` | GET | `/payout_settings` | read | Retrieves payout percentages and unique IDs for accounts configured to receive seller payo |
| `sell_account_v2.getRateTable` | GET | `/rate_table/{rate_table_id}` | read | Retrieves details of a specific shipping rate table. |
| `sell_account_v2.getUserPreferences` | GET | `/user_preferences` | read | Retrieves the seller's preferences for a specific eBay marketplace. |
| `sell_account_v2.setUserPreferences` | PATCH | `/user_preferences` | write | Modifies one or more preferences for a seller on a specific marketplace. |
| `sell_account_v2.updateCalculatedShippingRules` | POST | `/combined_shipping_rules/update_calculated_shipping_rules` | unknown | Updates previously defined calculated shipping rules. |
| `sell_account_v2.updateCombinedPayments` | POST | `/combined_shipping_rules/update_combined_payments` | unknown | Updates combined payment settings that determine how unpaid orders can be merged. |
| `sell_account_v2.updateFlatShippingRules` | POST | `/combined_shipping_rules/update_flat_shipping_rules` | unknown | Updates existing flat-rate shipping rules. |
| `sell_account_v2.updatePayoutPercentage` | POST | `/payout_settings/update_percentage` | unknown | Updates the split-payout percentage for two payout instruments for sellers in mainland Chi |
| `sell_account_v2.updatePromotionalShippingRule` | POST | `/combined_shipping_rules/update_promotional_shipping_rule` | unknown | Updates a promotional shipping rule to adjust discount thresholds, eligibility criteria, o |
| `sell_account_v2.updateShippingCost` | POST | `/rate_table/{rate_table_id}/update_shipping_cost` | unknown | Updates one or more shipping rates for a specific shipping rate table. |

Command path prefix: `bidkit sell account-v2 <operation>`.

## Examples

```bash
# sell_account_v2.createCalculatedShippingRules
bidkit sell account-v2 create-calculated-shipping-rules --body @request.json --format json --dry-run
# sell_account_v2.createFlatShippingRules
bidkit sell account-v2 create-flat-shipping-rules --body @request.json --format json --dry-run
# sell_account_v2.createPromotionalShippingRule
bidkit sell account-v2 create-promotional-shipping-rule --body @request.json --format json --dry-run
# sell_account_v2.getCombinedShippingRules
bidkit sell account-v2 get-combined-shipping-rules --format json
# sell_account_v2.getPayoutSettings
bidkit sell account-v2 get-payout-settings --format json
# sell_account_v2.getRateTable
bidkit sell account-v2 get-rate-table RATE-TABLE-ID --format json
# sell_account_v2.getUserPreferences
bidkit sell account-v2 get-user-preferences --format json
# sell_account_v2.setUserPreferences
bidkit sell account-v2 set-user-preferences --body @request.json --format json --dry-run
# sell_account_v2.updateCalculatedShippingRules
bidkit sell account-v2 update-calculated-shipping-rules --body @request.json --format json --dry-run
# sell_account_v2.updateCombinedPayments
bidkit sell account-v2 update-combined-payments --body @request.json --format json --dry-run
# sell_account_v2.updateFlatShippingRules
bidkit sell account-v2 update-flat-shipping-rules --body @request.json --format json --dry-run
# sell_account_v2.updatePayoutPercentage
bidkit sell account-v2 update-payout-percentage --body @request.json --format json --dry-run
# sell_account_v2.updatePromotionalShippingRule
bidkit sell account-v2 update-promotional-shipping-rule --body @request.json --format json --dry-run
# sell_account_v2.updateShippingCost
bidkit sell account-v2 update-shipping-cost RATE-TABLE-ID --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
