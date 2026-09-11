# The manifest names no standard hook file

[ADR 0051](0051-a-hook-refuses-and-a-seam-performs.md) added one key to the plugin
manifest:

```json
"hooks": "./hooks/hooks.json"
```

The key was correct when it was written. The harness then needed a manifest to point at a
hook file, and the key was how the plane installed with the skill.

The harness changed. It now loads `hooks/hooks.json` by convention, before it reads the
manifest. So the key names a file the harness already holds, and the load aborts:

```
❯ orchestrator-skills@wsza
    Status: ✘ failed to load
    Error: Hook load failed: Duplicate hooks file detected: ./hooks/hooks.json
    resolves to already-loaded file
    …/plugins/cache/wsza/orchestrator-skills/0.39.0/hooks/hooks.json.
    The standard hooks/hooks.json is loaded automatically, so manifest.hooks
    should only reference additional hook files.
```

**The failure is the whole plugin, and not the one hook.** Every skill goes with it. So a
key that was meant to make the enforcement automatic instead removed the three skills, the
two seams and the plane together.

## The decision

**`.claude-plugin/plugin.json` holds no `hooks` key.** The plane still ships, because the
harness reads the standard path on its own.

This reverses one paragraph of ADR 0051 and nothing else. The plane law of that ADR stands
unchanged: a hook answers, and a seam performs. The three hooks keep their events, their
content and their suites.

**A `hooks` key is still legal, for a second hook file.** The harness message says so: the
key exists to name an *additional* file. This repo has no second file, so this repo writes
no key.

## What follows from it

**The rollback moves.** ADR 0051 said the rollback was one line in the manifest. It is now
one file: rename or delete `hooks/hooks.json`, and the harness finds nothing at the standard
path.

**The setup report inverts.** Step 5b read 1 of `/orchestrator-setup` asserted that the
manifest printed `./hooks/hooks.json`, and it called any other value a dead plane. That test
passed on a broken plugin and failed on a working one. It now asserts the absence of the
key, and it names what a present key does.

## The accepted risk

**A convention is not a contract.** The manifest key was explicit, and the standard path is
implicit. A harness that later stops reading `hooks/hooks.json` by convention would take the
plane down with no error, because nothing in this repo would name the file.

The mitigation is step 5b of `/orchestrator-setup`, which already reads the three facts and
reports whether the plane is live. Read 2 opens `hooks/hooks.json` and prints its event
names, so a plane that stopped loading is one line in a setup report.

**The cost of the opposite choice is higher.** A manifest key that duplicates the standard
path takes down every skill in the plugin, and it does so on install, before any report can
run.

## Rejected: move the hook file to a second name

Keep the key, and point it at `hooks/plane.json`. The harness would then load the standard
path (absent) and the named file (present), with no duplicate.

Rejected. It renames a file three pages already name, to keep a key that buys nothing. The
convention gives the same result with one deletion.

## Rejected: keep the key and pin the harness version

Rejected. This repo pins no harness, and a plugin that loads only on one CLI version is a
plugin that fails silently for every other reader.
