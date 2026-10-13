// The harness table: one row per agent CLI a worker runs in, with the facts measured
// for each one. The entry point reads a role's `{harness, model, effort}`, checks it
// here, and starts the worker on the row's start path.
//
// The two start paths:
// - `agent`: orca launches the CLI itself, from `worker-start --agent <name>` plus the
//   row's flags, and adds the yolo flag on its own. Measured on orca 1.4.223, whose
//   codex launch ran `codex --dangerously-bypass-approvals-and-sandbox -m gpt-5.5 -c
//   model_reasoning_effort=low` for `--agent codex --model gpt-5.5 --effort low`.
// - `terminal`: orca's `--agent` does not know the CLI. The script creates a terminal
//   that runs `launch`, then binds it with `worker-start --terminal`, which still makes
//   a supervised Dispatch on the Run's mailbox. orca refuses `--model` and `--effort`
//   beside `--terminal`, so both ride in the launch line.

// The effort ladder a role may ask for, lowest first.
export const EFFORTS = ["low", "medium", "high", "xhigh", "max"] as const;

export type Effort = (typeof EFFORTS)[number];

export type Harness = {
  name: string;
  start: "agent" | "terminal";
  // The CLI a terminal start runs.
  bin: string;
  // The flags that let a worker act with no approval prompt.
  yolo: string[];
  // The model and effort flags, given the effort after the clamp. An agent row's flags
  // go to `worker-start`, and orca encodes them for the CLI. A terminal row's flags go
  // to the CLI itself.
  flags: (model: string, effort: Effort) => string[];
  // The efforts the CLI cannot take, each with the one it runs instead.
  clamp: Partial<Record<Effort, Effort>>;
  // The models the CLI launches, where it launches only one provider's.
  family?: { name: string; ids: RegExp };
  // Whether a prompt names a skill as a slash command.
  slash: boolean;
  // The agent id the `skills` CLI installs skills under, as of skills 1.7.2.
  skillsAgent: string;
  // The `orca terminal send` flags that answer the first-run "trust this folder?"
  // dialog, where one blocks the worker.
  trust?: string[];
};

const ANTHROPIC = { name: "anthropic", ids: /^(claude|opus|sonnet|haiku|fable)/i };
const OPENAI = { name: "openai", ids: /^(gpt|codex|o\d)/i };

// The one-row-per-harness table.
export const HARNESSES: Record<string, Harness> = {
  // The claude CLI's own aliases, such as `opus`, resolve on every provider.
  claude: {
    name: "claude",
    start: "agent",
    bin: "claude",
    yolo: ["--dangerously-skip-permissions"],
    flags: (model, effort) => ["--model", model, "--effort", effort],
    clamp: {},
    family: ANTHROPIC,
    slash: true,
    skillsAgent: "claude-code",
  },
  // orca writes `--effort` as `-c model_reasoning_effort=<effort>`. Under orca the
  // trust dialog does not block: the new worktree is marked trusted in
  // ~/.codex/config.toml, with no key pressed.
  codex: {
    name: "codex",
    start: "agent",
    bin: "codex",
    yolo: ["--dangerously-bypass-approvals-and-sandbox"],
    flags: (model, effort) => ["--model", model, "--effort", effort],
    clamp: { xhigh: "high", max: "high" },
    family: OPENAI,
    slash: false,
    skillsAgent: "codex",
  },
  // cursor-agent has no effort flag: the effort is part of the model id. An anthropic
  // model takes its `-thinking-` id, because the plain id runs with thinking off.
  cursor: {
    name: "cursor",
    start: "agent",
    bin: "cursor-agent",
    yolo: ["--force"],
    flags: (model, effort) => ["--model", ANTHROPIC.ids.test(model) ? `${model}-thinking-${effort}` : `${model}-${effort}`],
    clamp: {},
    slash: false,
    skillsAgent: "cursor",
  },
  // pi has no approval prompt. Enabling the tools a worker needs is its yolo flag. Its
  // model catalog is scoped to the account, so any model may be one it launches.
  pi: {
    name: "pi",
    start: "terminal",
    bin: "pi",
    yolo: ["-t", "read,bash,edit,write,grep,find,ls"],
    flags: (model, effort) => ["--model", model, "--thinking", effort],
    clamp: { max: "xhigh" },
    slash: false,
    skillsAgent: "pi",
  },
  // copilot asks "Do you trust the files in this folder?" in each new worktree, and
  // `--allow-all` does not answer it. Enter picks "Yes", for this session only.
  copilot: {
    name: "copilot",
    start: "terminal",
    bin: "copilot",
    yolo: ["--allow-all"],
    flags: (model, effort) => ["--model", model, "--effort", effort],
    clamp: {},
    slash: false,
    skillsAgent: "github-copilot",
    trust: ["--enter"],
  },
};

// A role checked against its harness: the row, the effort it runs at, and the clamp
// line where the effort changed.
export type Launch = { harness: Harness; model: string; effort: Effort; clamped?: string };

// The launch a role asks for, or the one reason it cannot start, worded to follow
// "its heavy role".
export function launchFor(role: { harness: string; model: string; effort: string }): Launch | string {
  const harness = HARNESSES[role.harness];
  if (!harness) return `names harness "${role.harness}", which is not one of ${Object.keys(HARNESSES).join(", ")}`;
  const asked = EFFORTS.find((effort) => effort === role.effort);
  if (!asked) return `asks effort "${role.effort}", which is not one of ${EFFORTS.join(", ")}`;
  if (harness.family && !harness.family.ids.test(role.model)) {
    return `pairs model "${role.model}" with ${harness.name}, which launches only ${harness.family.name} models`;
  }
  const effort = harness.clamp[asked] ?? asked;
  const clamped = effort === asked ? undefined : `effort ${asked} clamped to ${effort}, the most ${harness.name} takes`;
  return { harness, model: role.model, effort, clamped };
}

// The command a terminal start runs.
export function launchLine(launch: Launch): string[] {
  const { harness, model, effort } = launch;
  return [harness.bin, ...harness.yolo, ...harness.flags(model, effort)];
}

// How a prompt names skill `name`: `/name` on a harness that parses slash commands.
export function skill(harness: Harness, name: string): string {
  return harness.slash ? `/${name}` : `the \`${name}\` skill`;
}

// The imperative that runs skill `name`.
export function useSkill(harness: Harness, name: string): string {
  return `${harness.slash ? "Run" : "Use"} ${skill(harness, name)}`;
}
