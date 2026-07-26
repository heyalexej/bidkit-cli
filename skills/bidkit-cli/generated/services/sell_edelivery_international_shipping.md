# EDIS public shipping API

- **Service key:** `sell_edelivery_international_shipping`
- **CLI:** `bidkit sell edelivery-international-shipping`
- **Version:** 1.1.0
- **Base path:** `/sell/edelivery_international_shipping/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_edelivery_international_shipping_v1_oas3.json`
- **Operations:** 27

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_edelivery_international_shipping.OPERATION_ID
bidkit api schema sell_edelivery_international_shipping.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_edelivery_international_shipping.bulkCancelPackages` | POST | `/package/bulk_cancel_packages` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.bulkConfirmPackages` | POST | `/package/bulk_confirm_packages` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.bulkDeletePackages` | POST | `/package/bulk_delete_packages` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.cancelBundle` | POST | `/bundle/{bundle_id}/cancel` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.cancelPackage` | POST | `/package/{package_id}/cancel` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.clonePackage` | POST | `/package/{package_id}/clone` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.confirmPackage` | POST | `/package/{package_id}/confirm` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.createAddressPreference` | POST | `/address_preference` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.createBundle` | POST | `/bundle` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.createComplaint` | POST | `/complaint` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.createConsignPreference` | POST | `/consign_preference` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.createPackage` | POST | `/package` | unknown | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.deletePackage` | DELETE | `/package/{package_id}` | destructive | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getActualCosts` | GET | `/actual_costs` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getAddressPreferences` | GET | `/address_preference` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getAgents` | GET | `/agents` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getBatteryQualifications` | GET | `/battery_qualifications` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getBundle` | GET | `/bundle/{bundle_id}` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getBundleLabel` | GET | `/bundle/{bundle_id}/label` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getConsignPreferences` | GET | `/consign_preference` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getDropoffSites` | GET | `/dropoff_sites` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getHandoverSheet` | GET | `/handover_sheet` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getLabels` | GET | `/labels` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getPackage` | GET | `/package/{package_id}` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getPackagesByLineItemID` | GET | `/package/{order_line_item_id}/item` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getServices` | GET | `/services` | read | Important! This method is only available for Greater-China based sellers with an active eD |
| `sell_edelivery_international_shipping.getTracking` | GET | `/tracking` | read | Important! This method is only available for Greater-China based sellers with an active eD |

Command path prefix: `bidkit sell edelivery-international-shipping <operation>`.

## Examples

```bash
# sell_edelivery_international_shipping.bulkCancelPackages
bidkit sell edelivery-international-shipping bulk-cancel-packages --body @request.json --format json --dry-run
# sell_edelivery_international_shipping.bulkConfirmPackages
bidkit sell edelivery-international-shipping bulk-confirm-packages --body @request.json --format json --dry-run
# sell_edelivery_international_shipping.bulkDeletePackages
bidkit sell edelivery-international-shipping bulk-delete-packages --body @request.json --format json --dry-run
# sell_edelivery_international_shipping.cancelBundle
bidkit sell edelivery-international-shipping cancel-bundle BUNDLE-ID --format json --dry-run
# sell_edelivery_international_shipping.cancelPackage
bidkit sell edelivery-international-shipping cancel-package PACKAGE-ID --format json --dry-run
# sell_edelivery_international_shipping.clonePackage
bidkit sell edelivery-international-shipping clone-package PACKAGE-ID --format json --dry-run
# sell_edelivery_international_shipping.confirmPackage
bidkit sell edelivery-international-shipping confirm-package PACKAGE-ID --format json --dry-run
# sell_edelivery_international_shipping.createAddressPreference
bidkit sell edelivery-international-shipping create-address-preference --body @request.json --format json --dry-run
# sell_edelivery_international_shipping.createBundle
bidkit sell edelivery-international-shipping create-bundle --body @request.json --format json --dry-run
# sell_edelivery_international_shipping.createComplaint
bidkit sell edelivery-international-shipping create-complaint --body @request.json --format json --dry-run
# sell_edelivery_international_shipping.createConsignPreference
bidkit sell edelivery-international-shipping create-consign-preference --body @request.json --format json --dry-run
# sell_edelivery_international_shipping.createPackage
bidkit sell edelivery-international-shipping create-package --body @request.json --format json --dry-run
# sell_edelivery_international_shipping.deletePackage
bidkit sell edelivery-international-shipping delete-package PACKAGE-ID --format json --dry-run
# sell_edelivery_international_shipping.getActualCosts
bidkit sell edelivery-international-shipping get-actual-costs --format json
# sell_edelivery_international_shipping.getAddressPreferences
bidkit sell edelivery-international-shipping get-address-preferences --format json
# sell_edelivery_international_shipping.getAgents
bidkit sell edelivery-international-shipping get-agents --limit 30 --format json
# sell_edelivery_international_shipping.getBatteryQualifications
bidkit sell edelivery-international-shipping get-battery-qualifications --limit 30 --format json
# sell_edelivery_international_shipping.getBundle
bidkit sell edelivery-international-shipping get-bundle BUNDLE-ID --format json
# sell_edelivery_international_shipping.getBundleLabel
bidkit sell edelivery-international-shipping get-bundle-label BUNDLE-ID --format json
# sell_edelivery_international_shipping.getConsignPreferences
bidkit sell edelivery-international-shipping get-consign-preferences --format json
# sell_edelivery_international_shipping.getDropoffSites
bidkit sell edelivery-international-shipping get-dropoff-sites --limit 30 --format json
# sell_edelivery_international_shipping.getHandoverSheet
bidkit sell edelivery-international-shipping get-handover-sheet --tracking-numbers VALUE --format json
# sell_edelivery_international_shipping.getLabels
bidkit sell edelivery-international-shipping get-labels --tracking-numbers VALUE --format json
# sell_edelivery_international_shipping.getPackage
bidkit sell edelivery-international-shipping get-package PACKAGE-ID --format json
# sell_edelivery_international_shipping.getPackagesByLineItemID
bidkit sell edelivery-international-shipping get-packages-by-line-item-id ORDER-LINE-ITEM-ID --format json
# sell_edelivery_international_shipping.getServices
bidkit sell edelivery-international-shipping get-services --limit 30 --format json
# sell_edelivery_international_shipping.getTracking
bidkit sell edelivery-international-shipping get-tracking --tracking-number VALUE --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
