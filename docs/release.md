# Release runbook

Release an accepted development deployment through a PR from `dev` into
`main`. The gateway has its own SemVer tags and GitHub Releases.

## Prepare the candidate

Fetch the protected branches and tags.

```bash
git fetch origin --prune --tags
git tag -l 'v*' --sort=-version:refname | head
```

Choose the next version, then update `project.version` in `pyproject.toml` and
run `uv lock` on a branch based on `origin/dev`. Open a version-bump PR into
`dev` using [the Git workflow](git-workflow.md). Draft the release notes from
the PRs and commits since the previous tag. Include the changes users or
operators need to know about.

Run the complete local gate before opening the PR.

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
git diff --check
```

After the bump PR merges, confirm Woodpecker passed and deployed the exact
`origin/dev` SHA. Check public and loopback `/health`, OAuth and protected
resource metadata, and the unauthenticated MCP `401` challenge. When OAuth or
tools changed, complete a narrow real-client OAuth flow, run `tools/list`,
and call the smallest representative tool.

## Promote to production

Get the maintainer's approval after development acceptance. Open a release PR
with the version and release notes. Set `NEW` to the version tag, such as
`v0.2.1`, and `NOTES` to the release notes file. Recheck development
acceptance if `dev` advances while the PR is open.

```bash
gh pr create --base main --head dev --title "Release ${NEW}" --body-file "${NOTES}"
```

Wait for `ci/woodpecker/pr/test` to pass and merge using GitHub's
**Create a merge commit** option. The merge starts the production pipeline.
Confirm that the merge commit's tree matches the accepted development commit.

CI reruns the gate on the merge commit and deploys after it passes. Verify the
exact deployed SHA and the public and loopback health endpoints. Repeat the
applicable OAuth and tool checks from development. Keep the private operator
runbook handy for live SHA verification, deployment logs, and recovery commands.

## Tag and publish

Use the merge commit recorded by GitHub for the release PR. Confirm that it
matches the deployed SHA and carries the intended version. Set `PR` to the
merged release PR number.

```bash
git fetch origin main
MERGE=$(gh pr view "${PR}" --json mergeCommit --jq '.mergeCommit.oid')
git show "${MERGE}:pyproject.toml"
git tag -a "${NEW}" "${MERGE}" -m "${NEW} - <short title>" -F "${NOTES}"
git push origin "refs/tags/${NEW}"
gh release create "${NEW}" --verify-tag --latest \
  --title "${NEW} - <short title>" --notes-file "${NOTES}"
gh release view "${NEW}"
```

Leave `dev` at its own tip. The
release merge commit makes that tip an ancestor of `main`, so the next
release PR can merge without a sync back into `dev`.

## Recover from a failed release

Fix a failed candidate through a PR into `dev`. If production needs a rollback,
deploy the preceding known-good application SHA against the current additive
schema. Use the operator runbook for the rollback.

If the tag push fails, verify it points to the intended release merge commit
and retry that one ref. Once a tag or release is published, correct mistakes in
a new patch release and preserve the published tag.
