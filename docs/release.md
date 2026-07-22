# Release runbook

Use this runbook to publish a Meo MCP gateway release (`vX.Y.Z`). Routine work
lands on `dev`; `main` is the production release target.

## Core rules

- Release from an accepted `dev` deployment, never from an untested local tree.
- Keep the version in `pyproject.toml` equal to the release tag without its `v`
  prefix.
- Promote with an intentional non-fast-forward merge from `dev` into `main`.
- Create an annotated tag on the resulting `main` merge commit.
- Push only the intended tag; never use `git push --tags`.
- A pushed tag and a GitHub Release are separate objects. Publish both.
- Production migrations are additive. Roll back application code to a prior SHA
  without downgrading the database.
- Live targets, CI identifiers, credentials, and recovery commands stay in the
  private operator runbook.

## 1. Preflight

Run from the repository root:

```bash
git fetch --all --tags --prune
git status --short --branch
git branch --show-current
git tag -l 'v*' --sort=version:refname | tail -n 10
```

Confirm that:

- the current branch is `dev`
- the worktree contains only the intended release changes
- `dev` and `main` match their remote tracking branches before new commits
- no public diff contains credentials or private infrastructure inventory
- the previous release tag, if any, is known

## 2. Choose and record the version

Choose the next semantic version. For example:

```bash
NEW=v0.1.1
OLD=v0.1.0
```

Update `project.version` in `pyproject.toml` to `${NEW#v}`. Refresh the lockfile
when the version change affects it:

```bash
uv lock
rg -n 'version = "' pyproject.toml uv.lock
```

The first formal release may use the already-recorded project version when no
earlier tag exists.

## 3. Review and validate the release candidate

For an existing release history, review the delta:

```bash
git log --oneline --no-merges "${OLD}..HEAD"
git log --oneline --merges "${OLD}..HEAD"
git diff --stat "${OLD}..HEAD"
```

For the first release, review the full history and current tree instead. Then
run the complete local gates:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
git diff --check
```

Commit the release candidate deliberately on `dev`, including the version bump
when one is required:

```bash
git add <intended-paths>
git commit -m "<focused release-candidate message>"
git push origin dev
```

Wait for the development pipeline to succeed. Verify the exact deployed SHA,
the public and loopback `/health` endpoints, OAuth/resource metadata, and an
unauthenticated MCP `401` challenge. When auth behavior or the tool surface
changed, also complete a narrow real-client OAuth flow, `tools/list`, and the
smallest representative tool call.

## 4. Promote to production

Only after development acceptance:

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff dev -m "Merge dev into main for ${NEW} release"
```

Create an annotated tag on that merge commit. Draft a concise title, one short
summary paragraph, and flat bullets describing meaningful user-facing or
operator-facing changes:

```bash
git tag -a "${NEW}" \
  -m "${NEW} - <short title>" \
  -m "<release summary and bullet list>"
```

Push `main` first, monitor the production deployment to success, and verify its
exact SHA plus public/loopback health. Then publish only the intended tag:

```bash
git push origin main
git push origin "${NEW}"
```

Create the GitHub Release from the annotated tag:

```bash
gh release create "${NEW}" \
  --verify-tag \
  --notes-from-tag \
  --title "${NEW} - <short title>" \
  --latest
```

## 5. Post-release acceptance and branch sync

Verify the release object and production boundary:

```bash
git show -s --oneline "${NEW}"
gh release view "${NEW}"
curl -fsS https://mcp.meo-mai-moi.com/health
curl -fsS https://mcp.meo-mai-moi.com/.well-known/oauth-protected-resource/mcp
curl -fsS https://mcp.meo-mai-moi.com/.well-known/oauth-authorization-server
```

If OAuth behavior changed, reconnect a real client and confirm discovery plus a
narrow read call. If tools changed, verify their live schema and the least risky
representative call. Inspect only redacted logs and retain no tokens, callback
parameters, or personal tool output.

Finally, align `dev` with the production merge and accept the resulting
development deployment:

```bash
git checkout dev
git merge main --ff-only
git push origin dev
```

## Failure handling

- If local validation or the development pipeline fails, fix the candidate on
  `dev`; do not promote it.
- If the production pipeline fails after `main` is pushed, inspect redacted
  deployment logs and either fix forward through `dev` or deploy the preceding
  known-good application SHA. Do not downgrade the database.
- If the `main` push succeeds but the tag push fails, retry only the intended
  tag push after verifying where it points.
- If a published tag or release message is wrong, create a new patch version;
  do not rewrite published history.
- If the final `dev` synchronization fails, production remains authoritative;
  repair and synchronize `dev` before routine work resumes.

## Release note template

```text
vX.Y.Z - <short title>

<One short paragraph describing the release's intent and impact.>

- <Meaningful change 1>
- <Meaningful change 2>
- <Meaningful change 3>
```
