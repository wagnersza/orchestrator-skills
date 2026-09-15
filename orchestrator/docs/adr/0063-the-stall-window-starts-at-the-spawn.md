# The stall window starts at the spawn, so a fresh worker is never stalled

`0018-two-signals-and-no-guessed-progress.md` made the stall a fact about work
product. `0022-item-automation-replaces-the-blocking-watch.md` narrowed it to two
facts, and the tick reads the newer of the two: the checklist file's write time, and
the branch's last commit time. Neither one is a clock the seam owns, and that was
the point.

A worktree is cut from the default branch, so it starts life on a commit the worker
never made. That commit is as old as the last merge. It is often older than the whole
stall window at the moment of the spawn, and no amount of work makes it younger.

On 2026-09-11 that read as a healthy worker escalated to `needs-human` about two
minutes after its spawn. Work item #300 holds the measured timeline. The spawn wrote
the brief at `17:09:23`. The first tick fired at `17:10:42` and reported:

```
the newest work product in /Users/.../298-board-read-stops-at-100-cards is 1h 5m old
(the last commit), against a stall window of 45m 0s
```

The second tick, 62 seconds later, wrote `needs-human`. That label stops every later
tick, so the merge of that worker's pull request ran no **Close transaction**. The
worker itself was never stalled: it ran for four days, committed in three slices, and
finished with a green **Gate record**.

The window now starts at the newest of three facts, and the spawn is the third. The
spawn writes `.orchestrator/prompt-<item>.md` once, at its own step, and no worker
rewrites it. So its write time is when this worker started, and it is a fact on disk
the same way the other two are. The seam still owns no clock.

**A fresh worker is quiet whatever it inherited**, and it stays quiet until one window
passes after its own spawn. **No stall is taken away.** A worker that runs for the
window without writing a file still reads as `stalled`, because the spawn is then as
old as everything else.

This narrows `0018-two-signals-and-no-guessed-progress.md` and
`0022-item-automation-replaces-the-blocking-watch.md` in one place: the list of facts
the window reads. Every other part of both stands. That rest is the two signals, the
work product as the only evidence of progress, `dead` as the reviewer's own answer,
and the seam that writes no file of its own.

It also answers the inherited-commit cost that
`0026-the-automation-follows-the-live-worker.md` recorded and left standing. A
reviewer's fresh worktree starts on the implementation's commit, and that ADR
accepted the false stall. The reviewer's brief is written at its own spawn, so the
same third fact covers it.

## Considered Options

- **Read the spawn's own write of the brief as a third fact** (chosen) — the file is
  already there, in the directory the tick already reads, and the spawn already
  writes it. It costs one `stat` call and one `max`. Nothing new is stored, and a
  test moves the write time with `os.utime` rather than waiting for a real window.
- **Read only the commits the worker made, since the merge base with the default
  branch** — count no inherited commit at all. Rejected for this item, because it
  answers nothing for the first hour. A worker that made no commit yet has no commit
  fact, and the window still needs a start. It also puts a second git call on every
  tick, and it reads a default branch the seam does not hold.
- **Read the worktree directory's own creation time** — the truest spawn clock, and
  it needs no file. Rejected because a test cannot move it. `os.utime` sets the write
  time and never the birth time, so every stall case must wait a real window.
- **Give the tick a grace flag, so it reads no stall for the first N minutes** —
  rejected because a grace period is a second window to tune, and a caller that sets
  it wrong gets the same bug back. The spawn time is a fact, and a grace period is a
  guess about one.
- **Have the spawn write a start marker of its own** — one file whose only job is the
  clock. Rejected because the brief already carries that write time, and a second
  file is a second thing to seed, ignore and clean up.

## Consequences

- **The printed line names which of the three facts dated the window.** It reads
  `the spawn prompt-54.md is 3m 2s old` where the spawn is the newest, and it named
  only work product before. So a maintainer reads which clock answered.
- **A worktree with no brief keeps the old behaviour.** The fact is absent, so the
  window starts at the work product alone. A hand-made worktree and a spawn given
  `--prompt-file` outside the worktree both land there.
- **A real stall is reported later, by up to one window.** A worker that hangs in
  its first minute is reported one window after its spawn rather than on the first
  tick. `dead` is unchanged and still reports in about a minute, so a worker whose
  process is gone is caught as fast as it was.
- **The brief is now read by two seams.** `scripts/spawn_item.py` writes it and
  `scripts/worker_state.py` stats it. Its path is built the same way in both, from
  the item number, so a rename has two homes to visit.
