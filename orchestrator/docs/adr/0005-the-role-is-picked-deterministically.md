# The role is picked deterministically

Each issue runs on a role, and the role names its harness, model and effort. The tick
starts most workers, and the tick has no agent to judge an issue with. v1 picked the role
from prose signals that an agent read on every spawn, which cost tokens on every start.

## The decision

**Three roles, `heavy`, `medium` and `light`, each a harness, a model and an effort in
config.** Setup fills all three from a cost profile, and the human may change any one.

**The script picks the role in this order, and the first match wins:**

1. A manual `--role`, given on "work on N".
2. The heavy role label on the issue.
3. The light role label on the issue.
4. A `## Touches` block that lists at least `heavy_touches` paths: heavy.
5. Otherwise, medium.

**A manual start is the only time a role costs tokens**, and only when the human asks in
person. The main session may read the issue and pass `--role`.

**The script refuses a role its harness cannot run**, such as an openai model under
`claude`. It runs an effort the harness cannot take at the nearest effort below it, and the
start line says so.

## Rejected

- **An agent reading the issue on every spawn.** It spends tokens on every tick.
- **v1's prose heavy and light signals.** A script cannot read them.

## Consequences

The role of an issue is visible before it starts: read its labels and count its Touches. A
human who wants a different role adds a label or starts the issue by hand.
