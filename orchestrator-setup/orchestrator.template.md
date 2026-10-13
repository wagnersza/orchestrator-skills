# Orchestrator config

How the orchestrator runs workers in this repo. `scripts/orchestrator.ts` reads the first
fenced `json` block below. A field you leave out takes its default. Re-run the
`orchestrator-setup` skill to change it, or edit the block and keep it valid JSON.

```json
{
  "tracker": "{{tracker}}",
  "base": "{{base}}",
  "max_workers": {{max_workers}},
  "roles": {
    "heavy": { "harness": "{{heavy.harness}}", "model": "{{heavy.model}}", "effort": "{{heavy.effort}}" },
    "medium": { "harness": "{{medium.harness}}", "model": "{{medium.model}}", "effort": "{{medium.effort}}" },
    "light": { "harness": "{{light.harness}}", "model": "{{light.model}}", "effort": "{{light.effort}}" }
  },
  "role_labels": { "heavy": "heavy", "light": "light" },
  "heavy_touches": 3
}
```

## The fields

- **`tracker`**: `github`, `gitlab` or `local`. Setup reads it from
  `docs/agents/issue-tracker.md`, so the tracker is stated in one place. Default `github`.
- **`base`**: the branch each worktree starts from and each PR targets. Default `main`.
- **`max_workers`**: how many workers run at once. A parent issue takes no slot. Default `3`.
- **`roles`**: the `harness`, `model` and `effort` of each role. `harness` is one of
  `claude`, `codex`, `cursor`, `pi` and `copilot`. `effort` is one of `low`, `medium`,
  `high`, `xhigh` and `max`. A harness that cannot take an effort runs the nearest one
  below it, and the start line says so. A model the harness cannot launch, such as an
  openai model under `claude`, refuses the start.
- **`role_labels`**: the labels that pick a role. An issue with the `heavy` label runs on
  the heavy role, and one with the `light` label on the light role.
- **`heavy_touches`**: an issue with no role label runs on the heavy role when its
  `## Touches` block lists at least this many paths. Every other issue runs on the medium
  role. Default `3`.

`start N --role <role>` overrides the role pick for one start.
