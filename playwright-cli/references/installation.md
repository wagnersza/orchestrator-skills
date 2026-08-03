# Installing playwright-cli

Two things must be present before a browser session starts, and they install
separately:

1. **The CLI** — the `playwright-cli` binary, from the npm global package
   `@playwright/cli`. The skill body you are reading ships with the
   `orchestrator-skills` plugin. The binary does not.
2. **The browser binaries** — the Chromium, Firefox and WebKit builds the CLI
   drives, from `npx playwright install`.

A machine can have one without the other. Make sure that both are present, and
install what is missing.

Do the steps in order. Each command below ran on macOS, with the node from
Homebrew.

## 1. Prerequisites

The CLI is a node program, so `node` and `npm` must be on the PATH:

```bash
node --version    # v26.3.0
npm --version     # 11.16.0
```

If either command prints nothing, install node first (<https://nodejs.org>, or
`brew install node` on macOS). Then do step 2.

## 2. Install the CLI

```bash
npm install -g @playwright/cli
```

Then make sure that the binary is present, and read its version:

```bash
command -v playwright-cli    # /opt/homebrew/bin/playwright-cli
playwright-cli --version     # 0.1.17
```

`command -v` is the check that the dependency catalog uses. When the CLI is
present, it prints the path and exits 0. When the CLI is absent, it prints nothing
and exits 1.

The path is a symlink into the npm global directory:

```bash
ls -l /opt/homebrew/bin/playwright-cli
# -> ../lib/node_modules/@playwright/cli/playwright-cli.js
```

## 3. Install the browser binaries

```bash
npx playwright install
```

Add a browser name to get one browser instead of all of them:

```bash
npx playwright install chromium
```

The download goes to `~/Library/Caches/ms-playwright` on macOS, or to
`$PLAYWRIGHT_BROWSERS_PATH` when that variable is set. To see what is present:

```bash
ls -d "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"/chromium-*
```

## 4. Verify

`npm exited 0` is not proof. A browser must open. Run the three commands:

```bash
playwright-cli open https://example.com
playwright-cli list
playwright-cli close
```

The first command prints the page title, the generated Playwright code, and a
snapshot path:

````
### Browser `default` opened with pid 56431.
### Ran Playwright code
```js
await page.goto('https://example.com');
```
### Page
- Page URL: https://example.com/
- Page Title: Example Domain
````

`playwright-cli close` prints `Browser 'default' closed`. Then `playwright-cli
list` prints `(no browsers)`. The install is good when you see all three outputs.

## 5. Update

The CLI came from npm, so it updates through npm:

```bash
npm update -g @playwright/cli
```

Do **not** use `brew upgrade` for this. Homebrew owns the `node` that owns the
symlink. It does not own the package.

After a CLI update, install the browser binaries again. See
[Browsers missing after a CLI update](#browsers-missing-after-a-cli-update).

## Failure modes

### No node

`npm install -g @playwright/cli` fails with `command not found: npm`.

The CLI cannot install without node. Install node first. Then do step 2 again. An
unattended setup must stop here and tell the user, because a node install can need
a password.

### Browsers missing after a CLI update

`playwright-cli open` fails with a message about a missing executable, although
`command -v playwright-cli` prints a path.

A new CLI version can want a newer browser build than the one in the cache. The
cache keeps the old build, so the CLI check stays green and no session can start.
Run `npx playwright install` again. This failure is why the catalog reports the CLI
and the browsers as two requirements.

### A `playwright` on the PATH that is not this CLI

`command -v playwright` can print a path on a machine that has no
`@playwright/cli`. On the maintainer's machine it prints:

```
/Library/Frameworks/Python.framework/Versions/3.11/bin/playwright
```

That file is the entry point of the Python Playwright framework. It reports
`Version 1.40.0`, it is unrelated to `@playwright/cli`, and it accepts none of the
commands in this skill. A check that probes `playwright` reports green even when
the required CLI is absent.

**Always probe `playwright-cli`, with the suffix.** Never accept a bare
`playwright` as satisfaction.
