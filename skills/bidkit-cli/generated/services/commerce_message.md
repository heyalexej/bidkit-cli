# M2M Public API Service

- **Service key:** `commerce_message`
- **CLI:** `bidkit commerce message`
- **Version:** 1.0.0
- **Base path:** `/commerce/message/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_message_v1_oas3.json`
- **Operations:** 5

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_message.OPERATION_ID
bidkit api schema commerce_message.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_message.bulkUpdateConversation` | POST | `/bulk_update_conversation` | unknown | This method can be used to update the conversationStatus of up to 10 conversations. The co |
| `commerce_message.getConversation` | GET | `/conversation/{conversation_id}` | read | This method can be used to retrieve messages within a specific conversation. The conversat |
| `commerce_message.getConversations` | GET | `/conversation` | read | This method can be used to retrieve one or more conversations associated with a user. The  |
| `commerce_message.sendMessage` | POST | `/send_message` | unknown | This method can be used to start a conversation with another user or send a message in an  |
| `commerce_message.updateConversation` | POST | `/update_conversation` | unknown | This method can be used to update the conversationStatus or the read status of a specified |

Command path prefix: `bidkit commerce message <operation>`.

## Examples

```bash
# commerce_message.bulkUpdateConversation
bidkit commerce message bulk-update-conversation --body @request.json --format json --dry-run
# commerce_message.getConversation
bidkit commerce message get-conversation CONVERSATION-ID --conversation-type VALUE --limit 30 --format json
# commerce_message.getConversations
bidkit commerce message get-conversations --conversation-type VALUE --limit 30 --format json
# commerce_message.sendMessage
bidkit commerce message send-message --body @request.json --format json --dry-run
# commerce_message.updateConversation
bidkit commerce message update-conversation --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
