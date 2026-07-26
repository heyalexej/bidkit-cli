# Media API

- **Service key:** `commerce_media`
- **CLI:** `bidkit commerce media`
- **Version:** v1_beta.5.1
- **Base path:** `/commerce/media/v1_beta`  ·  **Subdomain:** `apim`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_media_v1_beta_oas3.json`
- **Operations:** 13

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_media.OPERATION_ID
bidkit api schema commerce_media.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_media.createDocument` | POST | `/document` | unknown | This method stages a document to be uploaded, and requires the type of document to be uplo |
| `commerce_media.createDocumentFromUrl` | POST | `/document/create_document_from_url` | unknown | This method downloads a document from the provided URL and adds that document to the user' |
| `commerce_media.createImageFromFile` | POST | `/image/create_image_from_file` | write | This method uploads a picture file to eBay Picture Services (EPS) using multipart/form-dat |
| `commerce_media.createImageFromUrl` | POST | `/image/create_image_from_url` | unknown | This method uploads a picture to eBay Picture Services (EPS) from the specified URL. Speci |
| `commerce_media.createVideo` | POST | `/video` | unknown | This method creates a video resource. When using this method, specify the title , size , a |
| `commerce_media.downloadPostOrderDocument` | GET | `/post_order/document/{document_id}` | read | This method downloads the file associated with the specified document ID. |
| `commerce_media.getDocument` | GET | `/document/{document_id}` | read | This method retrieves the current status and metadata of the specified document. Important |
| `commerce_media.getImage` | GET | `/image/{image_id}` | read | This method retrieves an EPS image URL and its expiration details for the unique identifie |
| `commerce_media.getVideo` | GET | `/video/{video_id}` | read | This method retrieves a video's metadata and content given a specified video ID . The meth |
| `commerce_media.removePostOrderDocument` | DELETE | `/post_order/document/{document_id}` | destructive | This method deletes a previously uploaded document by its document ID. Only documents in S |
| `commerce_media.uploadDocument` | POST | `/document/{document_id}/upload` | unknown | This method associates the specified file with the specified document ID and uploads the i |
| `commerce_media.uploadPostOrderDocument` | POST | `/post_order/document` | unknown | This method uploads a document for post‑order processes (for example, a seller providing a |
| `commerce_media.uploadVideo` | POST | `/video/{video_id}/upload` | unknown | This method associates the specified file with the specified video ID and uploads the inpu |

Command path prefix: `bidkit commerce media <operation>`.

## Examples

```bash
# commerce_media.createDocument
bidkit commerce media create-document --body @request.json --format json --dry-run
# commerce_media.createDocumentFromUrl
bidkit commerce media create-document-from-url --body @request.json --format json --dry-run
# commerce_media.createImageFromFile
bidkit commerce media create-image-from-file --file image=@./photo.JPG --dry-run --format json
# commerce_media.createImageFromUrl
bidkit commerce media create-image-from-url --body @request.json --format json --dry-run
# commerce_media.createVideo
bidkit commerce media create-video --body @request.json --format json --dry-run
# commerce_media.downloadPostOrderDocument
bidkit commerce media download-post-order-document DOCUMENT-ID --format json
# commerce_media.getDocument
bidkit commerce media get-document DOCUMENT-ID --format json
# commerce_media.getImage
bidkit commerce media get-image IMAGE-ID --format json
# commerce_media.getVideo
bidkit commerce media get-video VIDEO-ID --format json
# commerce_media.removePostOrderDocument
bidkit commerce media remove-post-order-document DOCUMENT-ID --format json --dry-run
# commerce_media.uploadDocument
bidkit commerce media upload-document DOCUMENT-ID --file file=@./file --format json --dry-run
# commerce_media.uploadPostOrderDocument
bidkit commerce media upload-post-order-document --file file=@./file --field documentUsageType=VALUE --format json --dry-run
# commerce_media.uploadVideo
bidkit commerce media upload-video VIDEO-ID --body-file ./input.bin --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
