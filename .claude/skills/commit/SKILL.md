---
name: commit
description: Run the project's checks and create a git commit in the repository's message style. Use when the user asks to commit changes.
disable-model-invocation: true
---

# Commit

Only commit when the user asks. Never push, amend, or rewrite history unless they ask for that too.

## Steps

1. **Look at what's changing**: `git status` and `git diff` (staged and unstaged). If the working tree mixes unrelated changes, propose separate commits instead of one.
2. **Run the checks that match the changed paths** (skip ones that clearly don't apply, and say which you skipped):
   - Rust (`backend/`, `lib/`, `migrations/`): `cargo fmt` (rustfmt.toml: max_width 140), then `cargo clippy --all-targets` (fix every warning; ask the user about any that need a decision), then `cargo test`. These already skip the Tauri crate.
   - Frontend (`frontend/`): `cd frontend && deno task fmt`, then `deno task lint` (fix every error; a suppression needs a comment saying why), `deno task test` and `deno task build`. A slug rule change also runs `cargo test -p backend slug`: `fixtures/slug_cases.json` is shared.
   - Docs/skills only: no checks needed.
   - Don't run `#[ignore]`d live tests; they hit the real BGG API and need a token.
   If a check fails, report the failure with its output and stop; don't commit a red tree unless the user says to.
3. **Stage explicitly** by path (`git add <files>`), not `git add -A`. Never stage `.env`, `*.db`, or other gitignored/secret files. `Cargo.lock` and `deno.lock` are committed, so include them when dependencies changed.
4. **Write the message** in the repository's style (see `git log --format=%s -n 20`):
   - one line, all lowercase, no trailing period, past tense, ending with the issue number in parentheses: "added user timeline endpoint and frontend types (#42)", "moved SQL into repositories and shared structs into models, leaving routes as thin handlers (#17)", "fixed expansions double counted in user collection (#8)";
   - the number is the issue the commit works on (the sub-issue in a tracking-issue flow, not the tracking issue or the PR). Take it from the user's message, else from the current branch's open PR (`gh pr view --json body`, its `Closes #` lines). If still unknown, **ask the user for it**; never guess, omit it or use the PR number. Merge commits are exempt;
   - say what changed and, when short, the shape of the result; name the area (backend, data-loader, frontend) in plain words rather than with a prefix like `feat:`;
   - add a body only when the why isn't obvious from the diff.
   Then append the attribution trailer given in the session's system instructions, if there is one. The subject line ends with the issue number; the trailer stays last in the body.
5. **Commit** with `git commit -m` (pass multi-line messages via multiple `-m` or a heredoc). Don't use `--no-verify`. If a hook fails, fix the cause and make a new commit.
6. **Report** the short hash and subject, and anything left uncommitted.

If on `main` and the user wants a PR, create a branch first.
