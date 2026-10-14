# The tick takes only what is assigned to me

`ready-for-agent` carries two meanings. To the triage skills it means "fully specified":
`to-tickets` and `to-spec` set it on each issue they file. To the tick it meant "go": the
tick claimed every eligible issue, and an unassigned issue was eligible
([ADR 0003](0003-state-labels-are-the-only-state.md)). So filing a spec started workers
before the human had read it.

## The decision

**This changes what the tick takes, not what is eligible. The tick takes an eligible issue
only once it is assigned to me, or once it is a child of a parent I hold.** A parent I hold
is an in-progress or ready-for-agent parent assigned to me. So assigning a story once lets
the tick claim it and run each child in order.

**"work on N" stays as it was.** The human's own verb is the go signal, so it still claims
an unassigned eligible issue, and on a parent it still starts each eligible child.

**`status` prints the ready queue the tick takes.** An eligible issue that is unassigned is
listed with the others that wait, and its reason names the assignee it waits for.

No skill assigns an issue as it files one, so assigning it is a step only the human takes.
A claim assigns me too, so a resumed `needs-human` issue is still mine, and the tick takes
it back once the human relabels it `ready-for-agent`.

## Rejected

- **A new go label beside `ready-for-agent`.** It is a fifth state label, against ADR 0003,
  and the triage skills do not know it.
- **Mapping the triage role to another label string in this repo.** It fixes one repo, and
  each repo setup writes keeps the problem.

## Consequences

`ready-for-agent` keeps its triage meaning, and the assignee becomes the go signal. Someone
who assigns an issue to me puts it in my tick's queue. An issue the tick waits on is no
different on the tracker from one that waits for any other reason, except for the
assignee.
