---
name: issue
description: Plan and implement a single (non-tracking) GitHub issue on its own branch and PR, with a plan for approval first, one commit, a stop for review with fixup commits for feedback, then squash and mark the PR ready. Use when the user asks to plan or work on an issue ("plan #42", "start #42", "do #42"), says "approved", or asks to finish one before merging. For a tracking issue with sub-issues, or work that splits into several related issues, use `tracking-issue` instead.
---

# Issue

A single issue (written by the user, with no sub-issues) is done on **its own branch** with **its own PR**. The flow is: **plan**, wait for approval, **implement** (one commit, pushed, draft PR), wait for review, address feedback with **fixup commits**, then on approval **squash** and **mark the PR ready**. The user merges.

The user drives the pace: never implement before the plan is approved, and never squash or mark ready before the commit is approved.

Find the repo with `gh repo view --json nameWithOwner --jq .nameWithOwner`, called `O/R` below.

The issue's body is the user's. Never edit it without asking; put the plan, decisions and results in comments.

## Modes

- **Plan** ("plan #42"): see [Plan](#plan).
- **Implement** ("approved", "go ahead" after a plan, "start #42"): see [Implement](#implement).
- **Feedback** on the pushed commit: see [Feedback](#feedback).
- **Approve** ("approved", "looks good" after a review): see [Approve](#approve).

If the user says "start #42" with no plan yet, do [Plan](#plan) first and stop for approval.

## Plan

Input: an issue the user created on GitHub. Planning creates only a comment; it never creates a branch, a commit or a PR.

1. **Read** the issue and all its comments (`gh issue view <n> --json body,comments,labels`), then the code it touches. If the issue turns out to have sub-issues (`gh api repos/O/R/issues/<n>/sub_issues`), stop and use `tracking-issue` instead. If the work needs more than one issue or commit that belong together, stop and say so, then use `tracking-issue` ([Draft](../tracking-issue/SKILL.md#draft)) rather than planning it here or splitting it into several standalone issues.
2. **Ask** about choices that belong to the user and are not settled (a backend change, a new dependency, removing behaviour, a schema change).
3. **Write the plan** as a comment on the issue (`gh issue comment <n> --body-file ...`) and show it in chat. It has these sections:
   - **Approach**: what changes and where, with `path:line` references, naming the project skills that will be used;
   - **Decisions**: the choices made and why, with the alternatives left out;
   - **Out of scope**: what is deliberately not touched; anything found along the way becomes a new issue (ask first), not a drive-by change;
   - **Verification**: the checks and the behaviour to confirm (see [Implement](#implement), step 3);
   - **Branch**: written as ``the branch `<branch>` ``, named `<n>-<short-slug>` (for example `42-user-timeline-paging`).
4. **Stop** for approval. Do not create the branch.

If the plan changes after the user's comments, edit the plan comment (`gh api -X PATCH repos/O/R/issues/comments/<id> -f body=...`) rather than adding a second one, and stop again.

## Implement

Only after the plan is approved.

1. **Branch and state.**
   - The branch is the one named in the plan comment. If it exists, check it out and `git pull`. Otherwise `git fetch`, then `git switch -c <branch> origin/main`.
   - The working tree must be clean first.
   - Re-read the issue's comments: the user's replies override the plan.
2. **Implement** only what the plan covers.
   - Use the project skills where they fit.
   - Keep CLAUDE.md and the project skills accurate in the same commit as the change that affects them.
   - A pure move or reformat goes in its own commit before the edits, so `git log --follow` and the review stay clean.
3. **Check**, by the paths changed (see the `commit` skill and CLAUDE.md):
   - Rust: `cargo fmt`, `cargo clippy --all-targets` (no warnings), `cargo test`.
   - Frontend: `deno task fmt:check`, `lint`, `test` and `build` from `frontend/`.
   - **Behaviour:** for UI changes, run both dev servers (`.claude/launch.json`) and use the pages in the browser pane. Test writes only on throwaway data created for the purpose and deleted afterwards. **Never change existing groups, game days or loaded data.**
   - **Tests:** when the change adds tests, break the code they cover on purpose and confirm a test fails, then restore it.
   - Clean up anything temporary: instrumentation, throwaway data, scratch files.
4. **Commit**, one commit for the issue (plus any separate move or format commit). Stage by path, never `git add -A`.
   - The message is the repo's style: one lowercase past-tense line saying what changed, with no prefix, ending with the issue's number: `... (#<n>)`. A separate move or format commit gets the same number.
   - End the message with the attribution trailer from the session instructions.
5. **Push** the branch (`git push -u origin <branch>`).
6. **Open a draft PR** (`gh pr create --draft`), titled like the commit subject. Its body is a short summary of what changed and how it was verified, `Closes #<n>`, and the PR attribution line. Then call the `ccd_pr` `get_status` and, if it does not report the PR, `bind_pr`.
7. **Comment** on the issue with `gh issue comment <n> --body-file ...`:
   - It starts `Done in <sha>.` Check the posted comment contains the SHA.
   - Then bullets: what changed and why, decisions that differ from the plan, how it was verified (with numbers where there are some), and what was **not** verified and why.
8. **Stop and report** in chat: the commit and PR link, what changed for the user, what was checked, what could not be checked, and the issue comment link. Ask for approval or changes.

## Feedback

When the user asks for changes before approving, make them as `git commit --fixup <sha>` of the commit they apply to. A fixup needs no number of its own: `fixup! <subject>` repeats the original one. Run the checks, push, and add a comment on the issue naming the fixup's SHA. Then stop and ask for approval again.

If the feedback changes the plan itself (a different approach, a new decision), say so in the comment and update the plan comment.

Use a plain follow-up commit (its subject also ending with `(#<n>)`) instead of a fixup only if the user wants the review history kept.

## Approve

When the user approves the commit (directly, or with "looks good"):

1. **Squash the fixups**, if there are any `fixup!` commits (`git log origin/main..HEAD --grep '^fixup!'`):
   ```
   BEFORE=$(git rev-parse 'HEAD^{tree}')
   GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash origin/main
   test "$(git rev-parse 'HEAD^{tree}')" = "$BEFORE"   # the final tree must be byte-identical
   git push --force-with-lease origin <branch>
   ```
   There is no backup branch: `git reflog` and the tree check are the safety net. If the check fails, `git reset --hard` back to `ORIG_HEAD` and report. The base is `origin/main`, so `git fetch` first and make sure the branch is not behind it (if it is, say so and ask before rebasing onto it).
2. **Fix the SHA** in the issue's `Done in <sha>` comment (and any fixup comments) with `gh api -X PATCH repos/O/R/issues/comments/<id> -f body=...`, when the squash changed it.
3. **Mark the PR ready:** `gh pr ready <pr>`. Then check `get_status` (the ccd_pr tools) for mergeability and CI, and offer Auto-fix if CI is red.
4. **Stop.** The user merges, with a merge commit so `main` keeps the issue's commit. Do not merge unless they ask. Afterwards, point out the remote branch they may want to delete.
