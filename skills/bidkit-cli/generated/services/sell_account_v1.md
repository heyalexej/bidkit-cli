# Account v1 API

- **Service key:** `sell_account_v1`
- **CLI:** `bidkit sell account`
- **Version:** v1.9.3
- **Base path:** `/sell/account/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_account_v1_oas3.json`
- **Operations:** 37

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_account_v1.OPERATION_ID
bidkit api schema sell_account_v1.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_account_v1.bulkCreateOrReplaceSalesTax` | POST | `/bulk_create_or_replace_sales_tax` | unknown | This method creates or updates multiple sales-tax table entries. Sales-tax tables can be s |
| `sell_account_v1.createCustomPolicy` | POST | `/custom_policy/` | unknown | This method creates a new custom policy that specifies the seller's terms for complying wi |
| `sell_account_v1.createFulfillmentPolicy` | POST | `/fulfillment_policy/` | unknown | This method creates a new fulfillment policy for an eBay marketplace where the policy enca |
| `sell_account_v1.createOrReplaceSalesTax` | PUT | `/sales_tax/{countryCode}/{jurisdictionId}` | write | This method creates or updates a sales-tax table entry for a jurisdiction. Specify the tax |
| `sell_account_v1.createPaymentPolicy` | POST | `/payment_policy` | unknown | This method creates a new payment policy where the policy encapsulates seller's terms for  |
| `sell_account_v1.createReturnPolicy` | POST | `/return_policy` | unknown | This method creates a new return policy where the policy encapsulates seller's terms for r |
| `sell_account_v1.deleteFulfillmentPolicy` | DELETE | `/fulfillment_policy/{fulfillmentPolicyId}` | destructive | This method deletes a fulfillment policy. Supply the ID of the policy you want to delete i |
| `sell_account_v1.deletePaymentPolicy` | DELETE | `/payment_policy/{payment_policy_id}` | destructive | This method deletes a payment policy. Supply the ID of the policy you want to delete in th |
| `sell_account_v1.deleteReturnPolicy` | DELETE | `/return_policy/{return_policy_id}` | destructive | This method deletes a return policy. Supply the ID of the policy you want to delete in the |
| `sell_account_v1.deleteSalesTax` | DELETE | `/sales_tax/{countryCode}/{jurisdictionId}` | destructive | This call deletes a sales-tax table entry for a jurisdiction. Specify the jurisdiction to  |
| `sell_account_v1.getAdvertisingEligibility` | GET | `/advertising_eligibility` | read | This method allows developers to check the seller eligibility status for eBay advertising  |
| `sell_account_v1.getCustomPolicies` | GET | `/custom_policy/` | read | This method retrieves the list of custom policies defined for a seller's account. To limit |
| `sell_account_v1.getCustomPolicy` | GET | `/custom_policy/{custom_policy_id}` | read | This method retrieves the custom policy specified by the custom_policy_id path parameter. |
| `sell_account_v1.getFulfillmentPolicies` | GET | `/fulfillment_policy` | read | This method retrieves all the fulfillment policies configured for the marketplace you spec |
| `sell_account_v1.getFulfillmentPolicy` | GET | `/fulfillment_policy/{fulfillmentPolicyId}` | read | This method retrieves the complete details of a fulfillment policy. Supply the ID of the p |
| `sell_account_v1.getFulfillmentPolicyByName` | GET | `/fulfillment_policy/get_by_policy_name` | read | This method retrieves the details for a specific fulfillment policy. In the request, suppl |
| `sell_account_v1.getKYC` | GET | `/kyc` | read | Note: This method was originally created to see which onboarding requirements were still p |
| `sell_account_v1.getOptedInPrograms` | GET | `/program/get_opted_in_programs` | read | This method gets a list of the seller programs that the seller has opted-in to. |
| `sell_account_v1.getPaymentPolicies` | GET | `/payment_policy` | read | This method retrieves all the payment business policies configured for the marketplace you |
| `sell_account_v1.getPaymentPolicy` | GET | `/payment_policy/{payment_policy_id}` | read | This method retrieves the complete details of a payment policy. Supply the ID of the polic |
| `sell_account_v1.getPaymentPolicyByName` | GET | `/payment_policy/get_by_policy_name` | read | This method retrieves the details of a specific payment policy. Supply both the policy nam |
| `sell_account_v1.getPaymentsProgram` | GET | `/payments_program/{marketplace_id}/{payments_program_type}` | read | Note: This method is no longer applicable, as all seller accounts globally have been enabl |
| `sell_account_v1.getPaymentsProgramOnboarding` | GET | `/payments_program/{marketplace_id}/{payments_program_type}/onboarding` | read | Note: This method is no longer applicable, as all seller accounts globally have been enabl |
| `sell_account_v1.getPrivileges` | GET | `/privilege` | read | This method retrieves the seller's current set of privileges, including whether or not the |
| `sell_account_v1.getRateTables` | GET | `/rate_table` | read | This method retrieves a seller's shipping rate tables for the country specified in the cou |
| `sell_account_v1.getReturnPolicies` | GET | `/return_policy` | read | This method retrieves all the return policies configured for the marketplace you specify u |
| `sell_account_v1.getReturnPolicy` | GET | `/return_policy/{return_policy_id}` | read | This method retrieves the complete details of the return policy specified by the returnPol |
| `sell_account_v1.getReturnPolicyByName` | GET | `/return_policy/get_by_policy_name` | read | This method retrieves the details of a specific return policy. Supply both the policy name |
| `sell_account_v1.getSalesTax` | GET | `/sales_tax/{countryCode}/{jurisdictionId}` | read | This call retrieves the current sales-tax table entry for a specific tax jurisdiction. Spe |
| `sell_account_v1.getSalesTaxes` | GET | `/sales_tax` | read | Use this call to retrieve all sales tax table entries that the seller has defined for a sp |
| `sell_account_v1.getSubscription` | GET | `/subscription` | read | This method retrieves a list of subscriptions associated with the seller account. |
| `sell_account_v1.optInToProgram` | POST | `/program/opt_in` | unknown | This method opts the seller in to an eBay seller program. Refer to the ProgramTypeEnum for |
| `sell_account_v1.optOutOfProgram` | POST | `/program/opt_out` | unknown | This method opts the seller out of a seller program in which they are currently opted in t |
| `sell_account_v1.updateCustomPolicy` | PUT | `/custom_policy/{custom_policy_id}` | write | This method updates an existing custom policy specified by the custom_policy_id path param |
| `sell_account_v1.updateFulfillmentPolicy` | PUT | `/fulfillment_policy/{fulfillmentPolicyId}` | write | This method updates an existing fulfillment policy. Specify the policy you want to update  |
| `sell_account_v1.updatePaymentPolicy` | PUT | `/payment_policy/{payment_policy_id}` | write | This method updates an existing payment policy. Specify the policy you want to update usin |
| `sell_account_v1.updateReturnPolicy` | PUT | `/return_policy/{return_policy_id}` | write | This method updates an existing return policy. Specify the policy you want to update using |

Command path prefix: `bidkit sell account <operation>`.

## Examples

```bash
# sell_account_v1.bulkCreateOrReplaceSalesTax
bidkit sell account bulk-create-or-replace-sales-tax --body @request.json --format json --dry-run
# sell_account_v1.createCustomPolicy
bidkit sell account create-custom-policy --body @request.json --format json --dry-run
# sell_account_v1.createFulfillmentPolicy
bidkit sell account create-fulfillment-policy --body @request.json --format json --dry-run
# sell_account_v1.createOrReplaceSalesTax
bidkit sell account create-or-replace-sales-tax COUNTRY-CODE JURISDICTION-ID --body @request.json --format json --dry-run
# sell_account_v1.createPaymentPolicy
bidkit sell account create-payment-policy --body @request.json --format json --dry-run
# sell_account_v1.createReturnPolicy
bidkit sell account create-return-policy --body @request.json --format json --dry-run
# sell_account_v1.deleteFulfillmentPolicy
bidkit sell account delete-fulfillment-policy FULFILLMENT-POLICY-ID --format json --dry-run
# sell_account_v1.deletePaymentPolicy
bidkit sell account delete-payment-policy PAYMENT-POLICY-ID --format json --dry-run
# sell_account_v1.deleteReturnPolicy
bidkit sell account delete-return-policy RETURN-POLICY-ID --format json --dry-run
# sell_account_v1.deleteSalesTax
bidkit sell account delete-sales-tax COUNTRY-CODE JURISDICTION-ID --format json --dry-run
# sell_account_v1.getAdvertisingEligibility
bidkit sell account get-advertising-eligibility --format json
# sell_account_v1.getCustomPolicies
bidkit sell account get-custom-policies --format json
# sell_account_v1.getCustomPolicy
bidkit sell account get-custom-policy CUSTOM-POLICY-ID --format json
# sell_account_v1.getFulfillmentPolicies
bidkit sell account get-fulfillment-policies --marketplace-id VALUE --format json
# sell_account_v1.getFulfillmentPolicy
bidkit sell account get-fulfillment-policy FULFILLMENT-POLICY-ID --format json
# sell_account_v1.getFulfillmentPolicyByName
bidkit sell account get-fulfillment-policy-by-name --marketplace-id VALUE --name VALUE --format json
# sell_account_v1.getKYC
bidkit sell account get-kyc --format json
# sell_account_v1.getOptedInPrograms
bidkit sell account get-opted-in-programs --format json
# sell_account_v1.getPaymentPolicies
bidkit sell account get-payment-policies --marketplace-id VALUE --format json
# sell_account_v1.getPaymentPolicy
bidkit sell account get-payment-policy PAYMENT-POLICY-ID --format json
# sell_account_v1.getPaymentPolicyByName
bidkit sell account get-payment-policy-by-name --marketplace-id VALUE --name VALUE --format json
# sell_account_v1.getPaymentsProgram
bidkit sell account get-payments-program MARKETPLACE-ID PAYMENTS-PROGRAM-TYPE --format json
# sell_account_v1.getPaymentsProgramOnboarding
bidkit sell account get-payments-program-onboarding MARKETPLACE-ID PAYMENTS-PROGRAM-TYPE --format json
# sell_account_v1.getPrivileges
bidkit sell account get-privileges --format json
# sell_account_v1.getRateTables
bidkit sell account get-rate-tables --format json
# sell_account_v1.getReturnPolicies
bidkit sell account get-return-policies --marketplace-id VALUE --format json
# sell_account_v1.getReturnPolicy
bidkit sell account get-return-policy RETURN-POLICY-ID --format json
# sell_account_v1.getReturnPolicyByName
bidkit sell account get-return-policy-by-name --marketplace-id VALUE --name VALUE --format json
# sell_account_v1.getSalesTax
bidkit sell account get-sales-tax COUNTRY-CODE JURISDICTION-ID --format json
# sell_account_v1.getSalesTaxes
bidkit sell account get-sales-taxes --country-code VALUE --format json
# sell_account_v1.getSubscription
bidkit sell account get-subscription --limit 30 --format json
# sell_account_v1.optInToProgram
bidkit sell account opt-in-to-program --body @request.json --format json --dry-run
# sell_account_v1.optOutOfProgram
bidkit sell account opt-out-of-program --body @request.json --format json --dry-run
# sell_account_v1.updateCustomPolicy
bidkit sell account update-custom-policy CUSTOM-POLICY-ID --body @request.json --format json --dry-run
# sell_account_v1.updateFulfillmentPolicy
bidkit sell account update-fulfillment-policy FULFILLMENT-POLICY-ID --body @request.json --format json --dry-run
# sell_account_v1.updatePaymentPolicy
bidkit sell account update-payment-policy PAYMENT-POLICY-ID --body @request.json --format json --dry-run
# sell_account_v1.updateReturnPolicy
bidkit sell account update-return-policy RETURN-POLICY-ID --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
