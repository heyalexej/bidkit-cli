# Commerce API namespace

Cross-cutting commerce APIs: catalog, charity, feedback, identity, **media** (uploads),
message, notification, taxonomy, translation, vero.

```bash
bidkit commerce identity get-user                                  # current user
bidkit commerce taxonomy get-default-category-tree-id --marketplace-id EBAY_US
bidkit commerce media create-image-from-file --file image=@p.jpg   # multipart; --allow-write-expert
```

`commerce_media` hosts the multipart/binary upload operations (see uploads-and-downloads.md).
