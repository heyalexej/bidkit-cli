# Uploads and downloads

## JSON request bodies

```bash
bidkit sell inventory create-or-replace-inventory-item SKU --body @item.json --allow-write
bidkit ... --body-json '{"product":{"title":"t"}}'        # inline
echo '{"product":{...}}' | bidkit ... --body @-           # stdin
```

Do **not** pass both `--body` and `--body-json`. If the operation references a Pydantic model,
the body is **validated** against it (field paths in any error) before dispatch; otherwise the
parsed JSON passes through untyped.

Inspect the exact schema first:

```bash
bidkit api schema sell_inventory.createOrReplaceInventoryItem request
```

## Multipart uploads

```bash
bidkit commerce media create-image-from-file --file image=@photo.jpg --allow-write

bidkit commerce media upload-post-order-document \
  --file file=@evidence.pdf \
  --field documentUsageType=RETURN \
  --field entityType=RETURN \
  --field entityId=R-0-1-2 \
  --allow-write-expert --yes
```

`--file NAME=@PATH` and `--field NAME=VALUE` are repeatable. Required file fields are enforced
before dispatch. File bytes are never base64-encoded unless the OAS requires it.

## Binary request bodies

```bash
bidkit commerce media upload-video --body-file video.mp4 --allow-write-expert --yes
```

The file is streamed/read per the SDK adapter; it is **never** parsed as UTF-8.

## Binary downloads (streamed, atomic)

```bash
bidkit sell logistics download-label-file SHIPMENT_ID --output-file label.pdf --force
```

Operations whose response is binary get a generated `stream_<method>` variant; the CLI uses
it for `--output-file` so the whole response is not held in memory. Bytes are written to a
temp file and atomically renamed on success; `--force` is required to overwrite an existing file.

## Signing

Finances API calls and selected refund operations require an RFC 9421 digital signature.
This is handled automatically when a signing key is configured — no CLI flag needed. The
manifest records `signing.required` per operation; `api describe` shows it.
