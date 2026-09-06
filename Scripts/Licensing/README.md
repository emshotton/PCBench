# Licensing scripts

`resolve_licenses.py` looks up the license of every board's source repository at the commit
that was current when the board was retrieved and writes, per board folder, a normalised
`licenses` entry in `metadata.json`, the verbatim `LICENSE` text and a `NOTICE.md`. It then
rebuilds `PCBs/master_metadata.json`, `LICENSES.md` and `github_meta/license_resolution.json`.

```
python3 Scripts/Licensing/resolve_licenses.py --dry-run          # counts only, writes nothing
python3 Scripts/Licensing/resolve_licenses.py                    # full run
python3 Scripts/Licensing/resolve_licenses.py --repo owner/name  # one repository
python3 -m pytest Scripts/Licensing                              # unit tests
```

It needs the GitHub CLI (`gh`) logged in. Responses are cached under `Scripts/Licensing/.cache/`
so a rerun after a crash or a rate-limit pause makes no repeated requests.
