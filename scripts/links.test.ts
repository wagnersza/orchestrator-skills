// Every relative link in every Markdown file of the repo names a file or a directory that
// exists. A URL and a bare `#anchor` are not checked.

import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

// Directories that hold no Markdown of this repo's own.
const SKIP = new Set([".git", "node_modules", ".orchestrator"]);

// `[text](target)`, with an optional title after the target.
const LINK = /\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)/g;

function markdownFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (SKIP.has(entry.name)) return [];
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return markdownFiles(path);
    return entry.name.endsWith(".md") ? [path] : [];
  });
}

// The text with fenced code blocks and inline code removed, so an example link is not read.
function prose(text: string): string {
  return text.replace(/^(```|~~~)[\s\S]*?^\1/gm, "").replace(/`[^`\n]*`/g, "");
}

function brokenLinks(file: string): string[] {
  return [...prose(readFileSync(file, "utf8")).matchAll(LINK)].flatMap((match) => {
    const target = match[1] ?? "";
    if (/^[a-z][a-z0-9+.-]*:/i.test(target) || target.startsWith("#")) return [];
    const path = decodeURIComponent(target.split("#")[0] ?? "");
    return existsSync(join(dirname(file), path)) ? [] : [`${relative(ROOT, file)}: ${target}`];
  });
}

test("every relative Markdown link resolves", () => {
  const files = markdownFiles(ROOT);
  assert.ok(files.length > 0, "found no Markdown files");
  assert.deepEqual(files.flatMap(brokenLinks), []);
});
