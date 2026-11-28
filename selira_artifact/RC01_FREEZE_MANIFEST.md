# RC01 technical freeze manifest

Status: source baseline recorded; local evidence preservation and anonymous export pending. Not a public release.

Source commit: `379d3f4f364a4d8bedc36100407ac1ad7d9a9943`. Scientific baseline: `255f664de346a9f65d5cc11c3f180067d3551e16`.

Operator reported the RC01 branch at the source commit with only a modified `evaluation/results/reproduced/multi_contract_lifecycle.json` and untracked `evaluation/results/reproduced/verification_report.json`. The following hashes describe local evidence, not necessarily Git blobs. They have not been independently recomputed by the repository reviewer. Preserve both local files before export. The two controlled TEP files share a checksum; retain both.

## Local evaluation evidence (SHA-256)

Paths relative to `evaluation/results/reproduced/`.

```text
74302A251A0E9ABEDC04A5B00FCBD13764875E24A72206901FD794D4EBE3ED0C  controlled_tep.json
74302A251A0E9ABEDC04A5B00FCBD13764875E24A72206901FD794D4EBE3ED0C  controlled_tep_initial.json
F0A443934655142A01C31C4EF419BAFFD627B6E2F79F655159F23F2552E2182F  multi_contract_baseline.json
C6F7D425EAAA5D33E973E1DF05B3A5EB3D9B4FA845954FFF3FB52AADF02BFA11  multi_contract_lifecycle.json
72DE71AA8AFCA610CFAF25E855E5FC9300884E76A9DB7E810743DFA9FB012904  representative_tep.json
CBC2C83C4687C4A87DB04131980A4BB2E7A37E60566684EAB2FC2F6FF861559D  selective_tep.json
3CB1F7C805B0548A0735C8D68EA90D6B3E6838FCD98CF1DCBC1F9A38E680DC21  tep_nexus_characterization.json
F85BD18C121CAEC3B5CB7531CB5B37626E16E57873ABD7EE5EBA0BF05977AB4E  unified_tep.json
BF8C8B1B64970586A8CA13CDCC72D243C684F4179B06AFF6C142CCB80DD90B34  verification_report.json
```

## Release gates

- Preserve original local evidence and verify hashes against the manifest.
- Sanitize a separate reviewer copy; recompute checksums for any changed files.
- Do not expose identifying commit references, paths or Git history in the reviewer copy; preserve required third-party notices.
- Upstream licensing and dataset redistribution rights remain unresolved. No public release or tag is authorized by this manifest.
- No scientific source, test, dataset or evaluation mechanism changes are made by this documentation commit.
