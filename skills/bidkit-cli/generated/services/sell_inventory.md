# Inventory API

- **Service key:** `sell_inventory`
- **CLI:** `bidkit sell inventory`
- **Version:** 1.18.5
- **Base path:** `/sell/inventory/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_inventory_v1_oas3.json`
- **Operations:** 36

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_inventory.OPERATION_ID
bidkit api schema sell_inventory.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_inventory.bulkCreateOffer` | POST | `/bulk_create_offer` | unknown | This call creates multiple offers (up to 25) for specific inventory items on a specific eB |
| `sell_inventory.bulkCreateOrReplaceInventoryItem` | POST | `/bulk_create_or_replace_inventory_item` | unknown | Note: Please note that any eBay listing created using the Inventory API cannot be revised  |
| `sell_inventory.bulkGetInventoryItem` | POST | `/bulk_get_inventory_item` | unknown | This call retrieves up to 25 inventory item records. The SKU value of each inventory item  |
| `sell_inventory.bulkMigrateListing` | POST | `/bulk_migrate_listing` | unknown | This call is used to convert existing eBay Listings to the corresponding Inventory API obj |
| `sell_inventory.bulkPublishOffer` | POST | `/bulk_publish_offer` | unknown | Note: Each listing can be revised up to 250 times in one calendar day. If this revision th |
| `sell_inventory.bulkUpdatePriceQuantity` | POST | `/bulk_update_price_quantity` | unknown | This call is used by the seller to update the total ship-to-home quantity of one inventory |
| `sell_inventory.createInventoryLocation` | POST | `/location/{merchantLocationKey}` | unknown | Use this call to create a new inventory location. In order to create and publish an offer  |
| `sell_inventory.createOffer` | POST | `/offer` | write | This call creates an offer for a specific inventory item on a specific eBay marketplace. I |
| `sell_inventory.createOrReplaceInventoryItem` | PUT | `/inventory_item/{sku}` | write | Note: Please note that any eBay listing created using the Inventory API cannot be revised  |
| `sell_inventory.createOrReplaceInventoryItemGroup` | PUT | `/inventory_item_group/{inventoryItemGroupKey}` | write | Note: Each listing can be revised up to 250 times in one calendar day. If this revision th |
| `sell_inventory.createOrReplaceProductCompatibility` | PUT | `/inventory_item/{sku}/product_compatibility` | write | This call is used by the seller to create or replace a list of products that are compatibl |
| `sell_inventory.createOrReplaceSkuLocationMapping` | PUT | `/listing/{listingId}/sku/{sku}/locations` | write | This method allows sellers to map multiple fulfillment center locations to single-SKU list |
| `sell_inventory.deleteInventoryItem` | DELETE | `/inventory_item/{sku}` | destructive | This call is used to delete an inventory item record associated with a specified SKU. |
| `sell_inventory.deleteInventoryItemGroup` | DELETE | `/inventory_item_group/{inventoryItemGroupKey}` | destructive | This call deletes the inventory item group for a given inventoryItemGroupKey value. |
| `sell_inventory.deleteInventoryLocation` | DELETE | `/location/{merchantLocationKey}` | destructive | This call deletes the inventory location that is specified in the merchantLocationKey path |
| `sell_inventory.deleteOffer` | DELETE | `/offer/{offerId}` | destructive | If used against an unpublished offer, this call will permanently delete that offer. In the |
| `sell_inventory.deleteProductCompatibility` | DELETE | `/inventory_item/{sku}/product_compatibility` | destructive | This call is used by the seller to delete the list of products that are compatible with th |
| `sell_inventory.deleteSkuLocationMapping` | DELETE | `/listing/{listingId}/sku/{sku}/locations` | destructive | This method allows sellers to remove all location mappings associated with a specific SKU  |
| `sell_inventory.disableInventoryLocation` | POST | `/location/{merchantLocationKey}/disable` | unknown | This call disables the inventory location that is specified in the merchantLocationKey pat |
| `sell_inventory.enableInventoryLocation` | POST | `/location/{merchantLocationKey}/enable` | unknown | This call enables a disabled inventory location that is specified in the merchantLocationK |
| `sell_inventory.getInventoryItem` | GET | `/inventory_item/{sku}` | read | This call retrieves the inventory item record for a given SKU. The SKU value is passed in  |
| `sell_inventory.getInventoryItemGroup` | GET | `/inventory_item_group/{inventoryItemGroupKey}` | read | This call retrieves the inventory item group for a given inventoryItemGroupKey value. The  |
| `sell_inventory.getInventoryItems` | GET | `/inventory_item` | read | This call retrieves all inventory item records defined for the seller's account. The limit |
| `sell_inventory.getInventoryLocation` | GET | `/location/{merchantLocationKey}` | read | This call retrieves all defined details of the inventory location that is specified by the |
| `sell_inventory.getInventoryLocations` | GET | `/location` | read | This call retrieves all defined details for every inventory location associated with the s |
| `sell_inventory.getListingFees` | POST | `/offer/get_listing_fees` | unknown | This call is used to retrieve the expected listing fees for up to 250 unpublished offers.  |
| `sell_inventory.getOffer` | GET | `/offer/{offerId}` | read | This call retrieves a specific published or unpublished offer. The unique identifier of th |
| `sell_inventory.getOffers` | GET | `/offer` | read | This call retrieves all existing offers for the specified SKU value. The seller has the op |
| `sell_inventory.getProductCompatibility` | GET | `/inventory_item/{sku}/product_compatibility` | read | This call is used by the seller to retrieve the list of products that are compatible with  |
| `sell_inventory.getSkuLocationMapping` | GET | `/listing/{listingId}/sku/{sku}/locations` | read | This method allows sellers to retrieve the locations mapped to a specific SKU within a lis |
| `sell_inventory.publishOffer` | POST | `/offer/{offerId}/publish` | write | Note: Each listing can be revised up to 250 times in one calendar day. If this revision th |
| `sell_inventory.publishOfferByInventoryItemGroup` | POST | `/offer/publish_by_inventory_item_group` | unknown | Note: Please note that any eBay listing created using the Inventory API cannot be revised  |
| `sell_inventory.updateInventoryLocation` | POST | `/location/{merchantLocationKey}/update_location_details` | unknown | Use this call to update location details for an existing inventory location. Specify the i |
| `sell_inventory.updateOffer` | PUT | `/offer/{offerId}` | write | This call updates an existing offer. An existing offer may be in published state (active e |
| `sell_inventory.withdrawOffer` | POST | `/offer/{offerId}/withdraw` | write | This call is used to end a single-variation listing that is associated with the specified  |
| `sell_inventory.withdrawOfferByInventoryItemGroup` | POST | `/offer/withdraw_by_inventory_item_group` | unknown | This call is used to end a multiple-variation eBay listing that is associated with the spe |

Command path prefix: `bidkit sell inventory <operation>`.

## Examples

```bash
# sell_inventory.bulkCreateOffer
bidkit sell inventory bulk-create-offer --body @request.json --format json --dry-run
# sell_inventory.bulkCreateOrReplaceInventoryItem
bidkit sell inventory bulk-create-or-replace-inventory-item --body @request.json --format json --dry-run
# sell_inventory.bulkGetInventoryItem
bidkit sell inventory bulk-get-inventory-item --body @request.json --format json --dry-run
# sell_inventory.bulkMigrateListing
bidkit sell inventory bulk-migrate-listing --body @request.json --format json --dry-run
# sell_inventory.bulkPublishOffer
bidkit sell inventory bulk-publish-offer --body @request.json --format json --dry-run
# sell_inventory.bulkUpdatePriceQuantity
bidkit sell inventory bulk-update-price-quantity --body @request.json --format json --dry-run
# sell_inventory.createInventoryLocation
bidkit sell inventory create-inventory-location MERCHANT-LOCATION-KEY --body @request.json --format json --dry-run
# sell_inventory.createOffer
bidkit sell inventory create-offer --body @request.json --format json --dry-run
# sell_inventory.createOrReplaceInventoryItem
bidkit sell inventory create-or-replace-inventory-item SKU --body @inventory-item.json --dry-run --format json
# sell_inventory.createOrReplaceInventoryItemGroup
bidkit sell inventory create-or-replace-inventory-item-group INVENTORY-ITEM-GROUP-KEY --body @request.json --format json --dry-run
# sell_inventory.createOrReplaceProductCompatibility
bidkit sell inventory create-or-replace-product-compatibility SKU --body @request.json --format json --dry-run
# sell_inventory.createOrReplaceSkuLocationMapping
bidkit sell inventory create-or-replace-sku-location-mapping LISTING-ID SKU --body @request.json --format json --dry-run
# sell_inventory.deleteInventoryItem
bidkit sell inventory delete-inventory-item SKU --format json --dry-run
# sell_inventory.deleteInventoryItemGroup
bidkit sell inventory delete-inventory-item-group INVENTORY-ITEM-GROUP-KEY --format json --dry-run
# sell_inventory.deleteInventoryLocation
bidkit sell inventory delete-inventory-location MERCHANT-LOCATION-KEY --format json --dry-run
# sell_inventory.deleteOffer
bidkit sell inventory delete-offer OFFER-ID --format json --dry-run
# sell_inventory.deleteProductCompatibility
bidkit sell inventory delete-product-compatibility SKU --format json --dry-run
# sell_inventory.deleteSkuLocationMapping
bidkit sell inventory delete-sku-location-mapping LISTING-ID SKU --format json --dry-run
# sell_inventory.disableInventoryLocation
bidkit sell inventory disable-inventory-location MERCHANT-LOCATION-KEY --format json --dry-run
# sell_inventory.enableInventoryLocation
bidkit sell inventory enable-inventory-location MERCHANT-LOCATION-KEY --format json --dry-run
# sell_inventory.getInventoryItem
bidkit sell inventory get-inventory-item SKU --format json
# sell_inventory.getInventoryItemGroup
bidkit sell inventory get-inventory-item-group INVENTORY-ITEM-GROUP-KEY --format json
# sell_inventory.getInventoryItems
bidkit sell inventory get-inventory-items --limit 30 --format json
# sell_inventory.getInventoryLocation
bidkit sell inventory get-inventory-location MERCHANT-LOCATION-KEY --format json
# sell_inventory.getInventoryLocations
bidkit sell inventory get-inventory-locations --limit 30 --format json
# sell_inventory.getListingFees
bidkit sell inventory get-listing-fees --body @request.json --format json --dry-run
# sell_inventory.getOffer
bidkit sell inventory get-offer OFFER-ID --format json
# sell_inventory.getOffers
bidkit sell inventory get-offers --sku VALUE --limit 30 --format json
# sell_inventory.getProductCompatibility
bidkit sell inventory get-product-compatibility SKU --format json
# sell_inventory.getSkuLocationMapping
bidkit sell inventory get-sku-location-mapping LISTING-ID SKU --format json
# sell_inventory.publishOffer
bidkit sell inventory publish-offer OFFER-ID --format json --dry-run
# sell_inventory.publishOfferByInventoryItemGroup
bidkit sell inventory publish-offer-by-inventory-item-group --body @request.json --format json --dry-run
# sell_inventory.updateInventoryLocation
bidkit sell inventory update-inventory-location MERCHANT-LOCATION-KEY --body @request.json --format json --dry-run
# sell_inventory.updateOffer
bidkit sell inventory update-offer OFFER-ID --body @offer-patch.json --dry-run --format json
# sell_inventory.withdrawOffer
bidkit sell inventory withdraw-offer OFFER-ID --format json --dry-run
# sell_inventory.withdrawOfferByInventoryItemGroup
bidkit sell inventory withdraw-offer-by-inventory-item-group --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
