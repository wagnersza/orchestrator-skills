# Orchestrator config

How the orchestrator runs workers in this repo. `scripts/orchestrator.ts` reads the first
fenced `json` block below. A field you leave out takes its default. Re-run the
`orchestrator-setup` skill to change it, or edit the block and keep it valid JSON.

```json
{
  "tracker": "github",
  "base": "main",
  "max_workers": 3,
  "roles": {
    "heavy": { "harness": "claude", "model": "opus", "effort": "high" },
    "medium": { "harness": "claude", "model": "sonnet", "effort": "medium" },
    "light": { "harness": "claude", "model": "sonnet", "effort": "low" }
  },
  "role_labels": { "heavy": "heavy", "light": "light" },
  "heavy_touches": 3
}
```

## The fields

- **`tracker`**: `github`, `gitlab` or `local`. Setup reads it from
  [`issue-tracker.md`](issue-tracker.md), so the tracker is stated in one place. Default
  `github`.
- **`base`**: the branch each worktree starts from and each PR targets. Default `main`.
- **`max_workers`**: how many workers the tick keeps running at once. A parent issue takes
  no slot. Default `3`.
- **`roles`**: the `harness`, `model` and `effort` of each role. This is the `balanced` cost
  profile. On `claude`, the model is the CLI's own alias, because it refuses a versioned id
  such as `sonnet-5`. `harness` is one of `claude`, `codex`, `cursor`, `pi` and `copilot`.
  `effort` is one of `low`, `medium`, `high`, `xhigh` and `max`. A harness that cannot take
  an effort runs the nearest one below it, and the start line says so. An openai model
  under `claude`, or an anthropic model under `codex`, refuses the start.
- **`role_labels`**: the labels that pick a role, on GitHub and GitLab. An issue with the
  `heavy` label runs on the heavy role, and one with the `light` label on the light role.
- **`heavy_touches`**: an issue with no role label runs on the heavy role when its
  `## Touches` block lists at least this many paths. Every other issue runs on the medium
  role. Default `3`.

`start N --role <role>` overrides the role pick for one start. The order of the pick is in
[ADR 0005](../../orchestrator/docs/adr/0005-the-role-is-picked-deterministically.md).
