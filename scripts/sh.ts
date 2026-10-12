// The one process runner. Every external command (gh, glab, orca, git, a harness CLI)
// runs through here, and every module takes a `Sh` as a dependency, so a test swaps in
// a fake that replays recorded output.

import { spawnSync } from "node:child_process";

export type Result = { code: number; stdout: string; stderr: string };

export type Sh = (cmd: string, args: string[], opts?: { cwd?: string; input?: string }) => Result;

// A command that cannot start (not installed, not executable) reads as exit 127, the
// shell's own code for it, so a caller sees one shape for every failure.
export const sh: Sh = (cmd, args, opts = {}) => {
  const run = spawnSync(cmd, args, {
    cwd: opts.cwd,
    input: opts.input,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (run.error) return { code: 127, stdout: "", stderr: run.error.message };
  return { code: run.status ?? 1, stdout: run.stdout, stderr: run.stderr };
};
