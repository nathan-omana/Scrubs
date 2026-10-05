# AGENTS.md

The full project spec is in [CLAUDE.md](CLAUDE.md). Read it before writing code.

## Git history was rewritten on Oct 5, 2026

History was rewritten twice on Oct 5. The code did not change either time, but commit IDs did:

1. Krish's old commit email (`krishkaushk@cs.sfu.ca`) was changed to `krish.z.kaushik@gmail.com` in every commit, on every branch.
2. Later that day, the commits authored by Claude on `main` were moved to Armin, and their Claude co-author lines were removed. That changed the IDs of most of `main` again. Every other branch was then deleted from GitHub (all were already merged into `main`). Start new work from `main`.

A clone made before either rewrite still has old IDs, and merging or pushing from it brings the old commits back as duplicates.

### Step 1: check whether this clone is old

Run both BEFORE any `git pull`, `git fetch`, `git merge` or `git push`:

```
git log --all --format='%ae %ce' | grep -c 'krishkaushk@cs.sfu.ca'
git rev-list --all | grep -c '^36fa9fcacef2c0b1eb1626f3c02cf1705949859b$'
```

The second command looks for one commit that only exists in history from before the second rewrite.

- Both print `0`: this clone is up to date. Ignore the rest of this section.
- Either prints more than `0`: this clone is old. Do not pull, merge or push. Do steps 2 to 6, in order.

### Step 2: save everything (before fetching)

```
git stash push -u -m "before-history-reset"   # only if `git status` shows changes
for b in $(git for-each-ref --format='%(refname:short)' refs/heads); do
  git branch -f "backup/$b" "$b"
  git rev-parse -q --verify "origin/$b" >/dev/null && git branch -f --no-track "oldbase/$b" "origin/$b"
done
```

`oldbase/<branch>` records where the OLD remote branch was, so step 4 can find your unpushed commits. It must be made before fetching.

### Step 3: get the new history

```
git fetch origin --prune --force --tags
```

### Step 4: move each branch onto the new history

For each local branch `<b>` that also exists on `origin`:

```
git checkout <b>
git reset --hard origin/<b>
git log --oneline oldbase/<b>..backup/<b>    # your unpushed commits, if any
git cherry-pick oldbase/<b>..backup/<b>      # skip if the log above was empty
```

If a cherry-pick conflicts, resolve it, `git add` the files, then `git cherry-pick --continue`. Stop and ask the user if unsure.

For a local branch with NO `origin/<b>` (never pushed): it was built on old `main`. Rebuild it on new main:

```
git checkout -b <b>-new origin/main
git log --oneline oldbase/main..backup/<b>    # only the commits that are yours on that branch
git cherry-pick <those commits, oldest first>
```

Then `git branch -D <b> && git branch -m <b>-new <b>`. If `oldbase/main` doesn't exist, show the user `git log backup/<b>` and ask which commits are theirs.

### Step 5: restore uncommitted work

```
git stash list            # if "before-history-reset" is there:
git stash pop
```

### Step 6: verify, then clean up

```
git log --format='%ae %ce' $(git for-each-ref --format='%(refname:short)' refs/heads | grep -v -e '^backup/' -e '^oldbase/') | grep -c 'krishkaushk@cs.sfu.ca'
git branch --contains 36fa9fcacef2c0b1eb1626f3c02cf1705949859b | grep -v -e 'backup/' -e 'oldbase/' | grep -c .
```

Both must print `0`. Show the user the result and the output of `git status`. Only after the user confirms everything looks right:

```
git for-each-ref --format='%(refname:short)' 'refs/heads/backup/' 'refs/heads/oldbase/' | xargs git branch -D
```

### Never

- Never `git pull` or `git merge` in a clone where step 1 printed more than `0`.
- Never push a branch that contains a commit with `krishkaushk@cs.sfu.ca`, or that contains commit `36fa9fcacef2c0b1eb1626f3c02cf1705949859b`.
- Never merge a pull request that adds dozens of commits already on `main`. That is old history coming back.
