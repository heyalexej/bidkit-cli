# Logistics API

- **Service key:** `sell_logistics`
- **CLI:** `bidkit sell logistics`
- **Version:** v1_beta.0.0
- **Base path:** `/sell/logistics/v1_beta`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_logistics_v1_oas3.json`
- **Operations:** 6

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_logistics.OPERATION_ID
bidkit api schema sell_logistics.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_logistics.cancelShipment` | POST | `/shipment/{shipmentId}/cancel` | unknown | This method cancels the shipment associated with the specified shipment ID and the associa |
| `sell_logistics.createFromShippingQuote` | POST | `/shipment/create_from_shipping_quote` | unknown | This method creates a shipment based on the shippingQuoteId and rateId values supplied in  |
| `sell_logistics.createShippingQuote` | POST | `/shipping_quote` | unknown | The createShippingQuote method returns a shipping quote that contains a list of live "rate |
| `sell_logistics.downloadLabelFile` | GET | `/shipment/{shipmentId}/download_label_file` | read | This method returns the shipping label file that was generated for the shipmentId value sp |
| `sell_logistics.getShipment` | GET | `/shipment/{shipmentId}` | read | This method retrieves the shipment details for the specified shipment ID. Call createFromS |
| `sell_logistics.getShippingQuote` | GET | `/shipping_quote/{shippingQuoteId}` | read | This method retrieves the complete details of the shipping quote associated with the speci |

Command path prefix: `bidkit sell logistics <operation>`.

## Examples

```bash
# sell_logistics.cancelShipment
bidkit sell logistics cancel-shipment SHIPMENT-ID --format json --dry-run
# sell_logistics.createFromShippingQuote
bidkit sell logistics create-from-shipping-quote --body @request.json --format json --dry-run
# sell_logistics.createShippingQuote
bidkit sell logistics create-shipping-quote --body @request.json --format json --dry-run
# sell_logistics.downloadLabelFile
bidkit sell logistics download-label-file SHIPMENT-ID --accept VALUE --format json
# sell_logistics.getShipment
bidkit sell logistics get-shipment SHIPMENT-ID --format json
# sell_logistics.getShippingQuote
bidkit sell logistics get-shipping-quote SHIPPING-QUOTE-ID --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
