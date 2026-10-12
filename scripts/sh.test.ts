// A thin smoke test of the real runner. Every other test uses a fake.

import assert from "node:assert/strict";
import { test } from "node:test";
import { sh } from "./sh.ts";

const node = process.execPath;

test("returns the exit code, stdout and stderr", () => {
  const run = sh(node, ["-e", "process.stdout.write('out'); process.stderr.write('err'); process.exit(3)"]);
  assert.deepEqual(run, { code: 3, stdout: "out", stderr: "err" });
});

test("passes stdin and the working directory", () => {
  const run = sh(node, ["-e", "process.stdin.pipe(process.stdout); process.stderr.write(process.cwd())"], {
    cwd: "/",
    input: "piped",
  });
  assert.deepEqual(run, { code: 0, stdout: "piped", stderr: "/" });
});

test("a command that cannot start exits 127", () => {
  const run = sh("no-such-command-349", []);
  assert.equal(run.code, 127);
  assert.match(run.stderr, /ENOENT/);
});
