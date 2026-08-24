# Tracker reads

The reads the flows need, with the exact command for each supported tracker CLI. One
read per section, and the heading is the query in the flow's own words. So a session
matches a need to a command, and it improvises nothing.

**Reads only.** A tracker write stays in the per-project
[`docs/agents/issue-tracker.md`](../../docs/agents/issue-tracker.md), with the label
vocabulary, the CLI name, the host and the board coordinates. Those are per-repo data.
The commands here are the same for every repo, so they live once
([ADR 0039](../docs/adr/0039-a-tracker-read-has-a-verified-command-in-the-skill.md)).

**Every command in this file ran against a real GitHub repo and a real GitLab project.**

Four placeholders. `<owner>/<name>` is the repository, `<N>` is a work-item number,
`<host>` is the GitLab server, and `<literal>` is the fixed string a count looks for.
On GitLab the project path carries the owner and the name joined by `%2F`. Where the
tracker is `gitlab.com`, drop `--hostname <host>`. Where the session already runs
inside the clone, drop `--repo`.

## Check a read before you parse it

**A tracker CLI that fails writes prose, not JSON.** `glab` writes a decorated error
block to standard error and leaves standard output empty. A parser on empty output
then raises `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`, which names
the parser and never names the cause.

**The exit code is the check.** Capture the read. Fold standard error into the captured
text. Then parse only after a zero exit:

```bash
out=$(<the read> 2>&1) || { printf 'tracker read failed: %s\n' "$out"; exit 1; }
printf '%s' "$out" | jq '<the filter>'
```

**A zero exit is not proof of JSON.** `glab issue list -F json` prints a text table and
exits 0. So the flag trap in this file is the second half of this rule.

**What a session reports on a failed read.** One line, with the command that ran and
the tracker's own first line. Then it stops: it spawns nothing, it writes no label, and
it moves no card. This is the same answer a tick gives with its `unreadable` outcome,
so a session and a tick report one failure one way
([`../CONTEXT.md`](../CONTEXT.md), **Worker watch**).

## Every child of a parent work item, closed children included

The children of a parent, whatever state each one is in. A parent close needs the closed
ones, because the open ones do not say which child closed last. Where the flows need it:
**Close a task** (the parent close), **The layer 5 story gate**, **Merge the queue**
step 7, **Resolve the item shape before you pick a flow**, and **"Work a #N"**.

The edge is the `## Parent` line of the child, per the `to-tickets` template
([`../CONTEXT.md`](../CONTEXT.md), **Work item**).

```bash
gh issue list --repo <owner>/<name> --state all --limit 200 \
  --json number,state,title,body \
  --jq '[.[] | select(.body | test("(?m)^## Parent\\s+#<N>\\b")) | {number, state, title}]'
```

```bash
glab api --hostname <host> "projects/<owner>%2F<name>/issues?state=all&per_page=100" \
  | jq '[.[] | select((.description // "") | test("(?m)^## Parent\\s+#<N>\\b")) | {iid, state, title}]'
```

`--limit` and `per_page` each cap the page. For a project with more items than the cap,
raise the cap or add `--paginate` to the `glab` read. `--paginate` prints one array per
page, so `jq -s add` joins them first.

## Every open item with its blockers

Every open item, its labels, and the items it waits on. This is the **Ready queue**
read, and the board reconcile runs on the same answer. Where the flows need it:
**"What next?"**, **"Work a #N"**, and **Board status**.

**A blocker that is absent from this answer is closed**, because the read holds every
open item. That is the ready predicate, with no second read
([`../CONTEXT.md`](../CONTEXT.md), **Ready queue**).

```bash
gh issue list --repo <owner>/<name> --state open --limit 200 \
  --json number,title,labels,body \
  --jq '[.[] | {number, title, labels: [.labels[].name],
                blocked_by: ([(.body // "") | splits("(?m)^## ")
                              | select(startswith("Blocked by")) | scan("#[0-9]+")] | unique)}]'
```

```bash
glab api --hostname <host> "projects/<owner>%2F<name>/issues?state=opened&per_page=100" \
  | jq '[.[] | {iid, title, labels,
                blocked_by: ([(.description // "") | splits("(?m)^## ")
                              | select(startswith("Blocked by")) | scan("#[0-9]+")] | unique)}]'
```

The numbers come from the `## Blocked by` section of the body. So a `#<n>` that the
prose of that section mentions reads as an edge too. Where a count decides something,
read the section itself.

## The count of comments that carry a literal

How many comments hold a fixed string. Two counts take this shape: the **Review
round** number is the count of `Verdict:` comments, and the stall count is the count of
`Stall:` comments for the worker's current `(Model, Effort)` pair. Where the flows need
it: **On the wake** (`stalled`), **Adversarial review**, and **Reporting to the user**.

Both literals are quoted here, so a writing pass leaves them byte-identical
([ADR 0023](../docs/adr/0023-the-stall-count-is-a-tracker-comment.md)).

```bash
gh issue view <N> --repo <owner>/<name> --json comments \
  --jq '[.comments[] | select(.body | contains("<literal>"))] | length'
```

```bash
glab api --hostname <host> "projects/<owner>%2F<name>/issues/<N>/notes?per_page=100" \
  | jq '[.[] | select(.body | contains("<literal>"))] | length'
```

GitLab calls a comment a note, and the notes endpoint also returns system notes such as
`mentioned in commit <sha>`. A fixed literal excludes them, so the read needs no filter
of its own.

## The labels and the comments on one work item

The two facts about one item. A flow reads the labels for the work state and the
**Phase**, and the comments for a count. Where the flows need it: **Resolve the item
shape before you pick a flow**, **On the wake**, and **Reporting to the user**.

```bash
gh issue view <N> --repo <owner>/<name> --json labels,comments \
  --jq '{labels: [.labels[].name], comments: [.comments[].body]}'
```

`glab` answers in two commands, and the host goes in a different place in each one:

```bash
glab issue view <N> -R <host>/<owner>/<name> -F json | jq '.labels'
glab api --hostname <host> "projects/<owner>%2F<name>/issues/<N>/notes?per_page=100" | jq '[.[].body]'
```

A label is a plain string on GitLab and an object with a `name` on GitHub. Both reads
are the pair `scripts/worker_state.py` already builds for a tick, so a session and a
tick read one item the same way.

## The `glab issue list` flag trap

`glab issue list` disagrees with every other `glab` command about its flags. Three
facts, each confirmed against `glab issue list --help`:

| Flag | What it means on `glab issue list` |
|---|---|
| `-O`, `--output` | the JSON flag. `text` or `json`, and `text` is the default |
| `-F`, `--output-format` | `details`, `ids` or `urls`. It is **not** the JSON flag |
| `--state` | it does not exist. Use `-A`/`--all`, or `-c`/`--closed` |

Two failures follow, and they fail in different ways:

- `glab issue list -O json --state all` prints `Unknown flag: --state.` and exits 1.
  Standard output is empty, so an unchecked parse raises `JSONDecodeError` and names no
  flag.
- `glab issue list -F json` prints a text table and **exits 0**. So only the parse
  fails, and the exit code says the read was fine.

`glab issue view` is the opposite: its `-F`, `--output` is the JSON flag. So the short
flag `-F` means two different things on two commands of one CLI. No read in this file
uses `glab issue list`, and the `glab api` form is why.

`gh issue list` takes `--state open|closed|all` and needs none of this.
