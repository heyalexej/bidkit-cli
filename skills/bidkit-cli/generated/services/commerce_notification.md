# Notification API

- **Service key:** `commerce_notification`
- **CLI:** `bidkit commerce notification`
- **Version:** v1.6.7
- **Base path:** `/commerce/notification/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_notification_v1_oas3.json`
- **Operations:** 21

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_notification.OPERATION_ID
bidkit api schema commerce_notification.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_notification.createDestination` | POST | `/destination` | unknown | This method allows applications to create a destination. A destination is an endpoint that |
| `commerce_notification.createSubscription` | POST | `/subscription` | unknown | This method allows applications to create a subscription for a topic and supported schema  |
| `commerce_notification.createSubscriptionFilter` | POST | `/subscription/{subscription_id}/filter` | unknown | This method allows applications to create a filter for a subscription. Filters allow appli |
| `commerce_notification.deleteDestination` | DELETE | `/destination/{destination_id}` | destructive | This method provides applications a way to delete a destination. The same destination ID c |
| `commerce_notification.deleteSubscription` | DELETE | `/subscription/{subscription_id}` | destructive | This method allows applications to delete a subscription. Subscriptions can be deleted reg |
| `commerce_notification.deleteSubscriptionFilter` | DELETE | `/subscription/{subscription_id}/filter/{filter_id}` | destructive | This method allows applications to disable the active filter on a subscription, so that a  |
| `commerce_notification.disableSubscription` | POST | `/subscription/{subscription_id}/disable` | unknown | This method disables a subscription, which prevents the subscription from providing notifi |
| `commerce_notification.enableSubscription` | POST | `/subscription/{subscription_id}/enable` | unknown | This method allows applications to enable a disabled subscription. To pause (or disable) a |
| `commerce_notification.getConfig` | GET | `/config` | read | This method allows applications to retrieve a previously created configuration. |
| `commerce_notification.getDestination` | GET | `/destination/{destination_id}` | read | This method allows applications to fetch the details for a destination. The details includ |
| `commerce_notification.getDestinations` | GET | `/destination` | read | This method allows applications to retrieve a paginated collection of destination resource |
| `commerce_notification.getPublicKey` | GET | `/public_key/{public_key_id}` | read | This method allows users to retrieve a public key using a specified key ID. The public key |
| `commerce_notification.getSubscription` | GET | `/subscription/{subscription_id}` | read | This method allows applications to retrieve subscription details for the specified subscri |
| `commerce_notification.getSubscriptionFilter` | GET | `/subscription/{subscription_id}/filter/{filter_id}` | read | This method allows applications to retrieve the filter details for the specified subscript |
| `commerce_notification.getSubscriptions` | GET | `/subscription` | read | This method allows applications to retrieve a list of all subscriptions. The list returned |
| `commerce_notification.getTopic` | GET | `/topic/{topic_id}` | read | This method allows applications to retrieve details for the specified topic. This informat |
| `commerce_notification.getTopics` | GET | `/topic` | read | This method returns a paginated collection of all supported topics, along with the details |
| `commerce_notification.testSubscription` | POST | `/subscription/{subscription_id}/test` | unknown · Triggers a real notification delivery to an external endpoint | This method triggers a mocked test payload that includes a notification ID, publish date,  |
| `commerce_notification.updateConfig` | PUT | `/config` | write | This method allows applications to create a new configuration or update an existing config |
| `commerce_notification.updateDestination` | PUT | `/destination/{destination_id}` | write | This method allows applications to update a destination. Note: The destination should be c |
| `commerce_notification.updateSubscription` | PUT | `/subscription/{subscription_id}` | write | This method allows applications to update a subscription. Subscriptions allow applications |

Command path prefix: `bidkit commerce notification <operation>`.

## Examples

```bash
# commerce_notification.createDestination
bidkit commerce notification create-destination --body @request.json --format json --dry-run
# commerce_notification.createSubscription
bidkit commerce notification create-subscription --body @request.json --format json --dry-run
# commerce_notification.createSubscriptionFilter
bidkit commerce notification create-subscription-filter SUBSCRIPTION-ID --body @request.json --format json --dry-run
# commerce_notification.deleteDestination
bidkit commerce notification delete-destination DESTINATION-ID --format json --dry-run
# commerce_notification.deleteSubscription
bidkit commerce notification delete-subscription SUBSCRIPTION-ID --format json --dry-run
# commerce_notification.deleteSubscriptionFilter
bidkit commerce notification delete-subscription-filter FILTER-ID SUBSCRIPTION-ID --format json --dry-run
# commerce_notification.disableSubscription
bidkit commerce notification disable-subscription SUBSCRIPTION-ID --format json --dry-run
# commerce_notification.enableSubscription
bidkit commerce notification enable-subscription SUBSCRIPTION-ID --format json --dry-run
# commerce_notification.getConfig
bidkit commerce notification get-config --format json
# commerce_notification.getDestination
bidkit commerce notification get-destination DESTINATION-ID --format json
# commerce_notification.getDestinations
bidkit commerce notification get-destinations --limit 30 --format json
# commerce_notification.getPublicKey
bidkit commerce notification get-public-key PUBLIC-KEY-ID --format json
# commerce_notification.getSubscription
bidkit commerce notification get-subscription SUBSCRIPTION-ID --format json
# commerce_notification.getSubscriptionFilter
bidkit commerce notification get-subscription-filter FILTER-ID SUBSCRIPTION-ID --format json
# commerce_notification.getSubscriptions
bidkit commerce notification get-subscriptions --limit 30 --format json
# commerce_notification.getTopic
bidkit commerce notification get-topic TOPIC-ID --format json
# commerce_notification.getTopics
bidkit commerce notification get-topics --limit 30 --format json
# commerce_notification.testSubscription
bidkit commerce notification test-subscription SUBSCRIPTION-ID --format json --dry-run
# commerce_notification.updateConfig
bidkit commerce notification update-config --body @request.json --format json --dry-run
# commerce_notification.updateDestination
bidkit commerce notification update-destination DESTINATION-ID --body @request.json --format json --dry-run
# commerce_notification.updateSubscription
bidkit commerce notification update-subscription SUBSCRIPTION-ID --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
