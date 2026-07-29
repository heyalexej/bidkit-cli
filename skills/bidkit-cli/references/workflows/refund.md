# Workflow: issue a refund (signed)

`sell_fulfillment.issueRefund` is a **signed**, `unknown`-risk POST. It requires a configured
signing key *and* an explicit override.

## 1. Confirm signing is configured (offline)

```bash
bidkit auth doctor    # signing.configured + signing.parseable should both be true
```

## 2. Inspect the request model (offline)

```bash
bidkit api schema sell_fulfillment.issueRefund request
bidkit api describe sell_fulfillment.issueRefund   # signing.required: true
```

## 3. Dry-run (no network, no token)

```bash
bidkit sell fulfillment issue-refund ORDER LINE --body @refund.json --dry-run
```

## 4. Execute (expert override)

```bash
bidkit sell fulfillment issue-refund ORDER LINE \
  --body @refund.json --allow-write-expert --yes --format json
```

Post-order refund equivalents (`return.issueReturnRefund`, `case.issueCaseRefund`,
`inquiry.issueInquiryRefund`, `return.processReturnRequest`,
`cancellation.approveCancellationRequest`, `cancellation.createCancellation`) are also signed.

Always confirm with a read afterward (`getReturn`, `getCase`, etc.).
