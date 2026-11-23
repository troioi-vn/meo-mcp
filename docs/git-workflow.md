# Git workflow

Open a PR into `dev` for each change. A merge into `dev` deploys the development
gateway. Releases go through a PR from `dev` into `main`, which deploys production.
Both branches are protected, including for admins.

Start each change from the current `origin/dev` in its own worktree:

```bash
git fetch origin --prune
git worktree add -b feat/your-change ../meo-mcp-your-change origin/dev
cd ../meo-mcp-your-change
uv sync --all-groups
```

Run the relevant local checks, commit the change, and open its PR:

```bash
git push -u origin feat/your-change
gh pr create --base dev --fill
```

Woodpecker's `ci/woodpecker/pr/test` status covers pytest, Ruff lint, and Ruff
formatting. Fork pipelines wait for a maintainer to approve the run. Purrequest
reviews same-repository PRs into `dev` once CI reports. It posts a public comment.
Fix its findings or reply on the PR so the next review can see what you decided.
Use `@purrequest` on the PR to request a follow-up review after pushing a fix.

Leave the merge to the maintainer. After the PR lands, remove the worktree and
delete the feature branch once you've checked for uncommitted work.

See [the release runbook](release.md) for production promotion.
