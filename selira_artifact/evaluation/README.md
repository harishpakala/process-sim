# Reproduce the integrated evaluation

From the artifact root after editable installation:

```sh
python evaluation/characterize_dataset.py
python evaluation/multi_contract_baseline.py
python evaluation/multi_contract_lifecycle.py
```

Archived results are byte-identical copies from the integration baseline; new outputs go to results/reproduced. Expected: 182 focus pairs, 25502 union triples, 11 submissions (5 V, 5 F, 1 U), 9 equivalent comparisons, 195/1638 logical evaluations. These are historical targets, not newly verified results. Dataset redistribution rights must be confirmed before independent release. The lifecycle input hash keys change with directory layout; hash values should remain unchanged. Policy files are not included in the historical script's hash manifest. No timing improvement is claimed.
