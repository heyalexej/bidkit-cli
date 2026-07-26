# Post-Order API namespace

Post-order case/inquiry/cancellation/return management. Exposed as `post-order` on the CLI.

These services use the **TOKEN** auth scheme (see `api describe ... auth.scheme`) and several
operations require a digital signature (`issueCaseRefund`, `issueReturnRefund`,
`processReturnRequest`, `approveCancellationRequest`, `createCancellation`).

```bash
bidkit post-order return search --order_id 12-12345-12345
bidkit post-order return get-return R-0-1-2
```

The canonical key keeps the underscore (`return.getReturn`); the command path uses
`post-order return get-return`.
