# Skills

Skills are reviewed Markdown instructions that help the model use the harness consistently. They are not plugins, executable code, or a way to grant new tools.

## File format

Each skill is a `SKILL.md` with frontmatter followed by Markdown:

```markdown
---
name: analyze-cs2-round
description: Runs and explains a seeded CS2 simulation using approved tools.
compatibility: Requires the CS2 harness tool registry.
---

# Analyze a CS2 round

Use `simulate_round` for one bounded scenario and seed.
```

The loader requires a lowercase kebab-case `name` (up to 64 characters) and a non-empty `description` (up to 1024 characters). The optional `compatibility` field documents assumptions for reviewers; it does not change permissions.

## Discovery and loading

Pass one or more explicit directories with the CLI's `--skill-dir` option or the session `skillDirs` configuration. Discovery is recursive, deterministic, and limited to files named exactly `SKILL.md`. Malformed frontmatter, invalid names, unreadable directories, and duplicate names fail session startup. Global Pi skills and extensions are disabled, so a skill is loaded only when the host opts in to its directory.

The current skill is [`analyze-cs2-round`](../skills/analyze-cs2-round/SKILL.md). It instructs the model to use bounded simulations, ground claims in returned events, and distinguish simulator behavior from real professional advice.

## Authoring guidance

- State when the skill should be used and which approved tools it may call.
- Prefer a short, progressive workflow over a large reference dump.
- Keep bounds, uncertainty, and evidence requirements explicit.
- Never put credentials, secrets, shell commands, or hidden-state claims in a skill.
- Review a skill as prompt content: it can influence model behavior, but policy and tool validation remain authoritative.
