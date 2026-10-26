# Eval cases

Each case: `cases/<id>/photo-*.{jpg,webp}` + `expected.docmodel.json` (hand-checked ground truth).

**Personal data warning:** real cases may contain passports, INN, phones and addresses.
Keep this directory private; do not publish the repository with real cases in it.

Ground-truth rules:
- Block text is verbatim, typos included. Probable typos go to `suggestions`.
- Handwritten edits go to `corrections` only; block text stays as printed.
