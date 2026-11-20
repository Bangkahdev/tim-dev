# WS9 Evidence — Repository, Secrets, and Archive Health

**Date:** 2026-11-20
**Status:** **PARTIAL.** Repository history is clean and stale files are
removed. Two items still require the repository owner: the visibility decision
(see below) and evidence archives stored in two locations with a SHA-256
manifest.

## Audit results

### Sensitive paths in history

```bash
git log --all --oneline -- backend/.env backend/data/office.db .cloudflare
```

Result: **no commits**. The local `backend/.env` and `backend/data/office.db`
were never tracked.

### Tracked sensitive-looking files

```bash
git ls-files | grep -Ei '(^|/)\.env($|\.)|office\.db|\.crt$|\.key$|\.pem$|\.cloudflare'
```

Result: only `backend/.env.example` (placeholder values, no credentials).

### Ignore rules verified

```bash
git check-ignore -v backend/.env backend/data/office.db
```

- `backend/.gitignore:2:.env` covers `backend/.env`.
- `backend/.gitignore:16:data/` covers `backend/data/office.db`.

`.gitattributes` applies LF normalization to source, docs, JSON, YAML, shell,
and Godot text files.

### Leftovers removed

| Path | Reason |
| --- | --- |
| `package-lock.json` (root) | Empty lockfile with no root `package.json` |
| `godot/scripts/main.gd.bak` | Stale editor backup (last touched 2026-11-03) |
| `_envpatch_tmp/` | Tracked scratch copies of `safe_env.py`, `main.py`, `test_safe_env.py`; no references in the repository |

`.gitignore` now also blocks `*.bak`, `*.orig`, `*.rej`, `*.tmp`, and
`_envpatch_tmp/` so these files cannot be re-added by accident.

## Open items for the repository owner

1. **Visibility.** The plan's G9 requires a private repository. The current
   GitHub repository `Bangkahdev/tim-dev` is **public**. No secrets were found
   in history, so this is a policy decision rather than an incident: either
   switch the repository to private before Stage 2, or record an explicit
   decision that public is intended.
2. **Archive in two locations.** The M1/WS2 evidence archives still need to be
   copied to a second location and accompanied by a SHA-256 manifest.
3. **CI.** Confirm the final `main` run is green after this cleanup PR merges.

## Honesty boundary

This audit covers the local Git history and tracked files reachable from this
clone. It does not scan GitHub-only branches that are not fetched, GitHub
Actions logs, forks, or cached copies outside the repository.
