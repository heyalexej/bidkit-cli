# Order V2 API

- **Service key:** `buy_order`
- **CLI:** `bidkit buy order`
- **Version:** v2.1.4
- **Base path:** `/buy/order/v2`  ·  **Subdomain:** `apix`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `buy_order_v1_beta_oas3.json`
- **Operations:** 8

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe buy_order.OPERATION_ID
bidkit api schema buy_order.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `buy_order.applyGuestCoupon` | POST | `/guest_checkout_session/{checkoutSessionId}/apply_coupon` | unknown | Note: The Order V2 API supports guest checkout payment flows. If you need to support membe |
| `buy_order.getGuestCheckoutSession` | GET | `/guest_checkout_session/{checkoutSessionId}` | read | Note: The Order V2 API supports guest checkout payment flows. If you need to support membe |
| `buy_order.getGuestPurchaseOrder` | GET | `/guest_purchase_order/{purchaseOrderId}` | read | Note: The Order V2 API supports guest checkout payment flows. If you need to support membe |
| `buy_order.initiateGuestCheckoutSession` | POST | `/guest_checkout_session/initiate` | unknown | Note: The Order V2 API supports guest checkout payment flows. If you need to support membe |
| `buy_order.removeGuestCoupon` | POST | `/guest_checkout_session/{checkoutSessionId}/remove_coupon` | unknown | Note: The Order V2 API supports guest checkout payment flows. If you need to support membe |
| `buy_order.updateGuestQuantity` | POST | `/guest_checkout_session/{checkoutSessionId}/update_quantity` | unknown | Note: The Order V2 API supports guest checkout payment flows. If you need to support membe |
| `buy_order.updateGuestShippingAddress` | POST | `/guest_checkout_session/{checkoutSessionId}/update_shipping_address` | unknown | Note: The Order V2 API supports guest checkout payment flows. If you need to support membe |
| `buy_order.updateGuestShippingOption` | POST | `/guest_checkout_session/{checkoutSessionId}/update_shipping_option` | unknown | Note: The Order V2 API supports guest checkout payment flows. If you need to support membe |

Command path prefix: `bidkit buy order <operation>`.

## Examples

```bash
# buy_order.applyGuestCoupon
bidkit buy order apply-guest-coupon CHECKOUT-SESSION-ID --body @request.json --format json --dry-run
# buy_order.getGuestCheckoutSession
bidkit buy order get-guest-checkout-session CHECKOUT-SESSION-ID --format json
# buy_order.getGuestPurchaseOrder
bidkit buy order get-guest-purchase-order PURCHASE-ORDER-ID --format json
# buy_order.initiateGuestCheckoutSession
bidkit buy order initiate-guest-checkout-session --body @request.json --format json --dry-run
# buy_order.removeGuestCoupon
bidkit buy order remove-guest-coupon CHECKOUT-SESSION-ID --body @request.json --format json --dry-run
# buy_order.updateGuestQuantity
bidkit buy order update-guest-quantity CHECKOUT-SESSION-ID --body @request.json --format json --dry-run
# buy_order.updateGuestShippingAddress
bidkit buy order update-guest-shipping-address CHECKOUT-SESSION-ID --body @request.json --format json --dry-run
# buy_order.updateGuestShippingOption
bidkit buy order update-guest-shipping-option CHECKOUT-SESSION-ID --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
