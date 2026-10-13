# The gates: the TypeScript typecheck, then the node --test suite.

.PHONY: quick full

quick: node_modules
	npm run --silent typecheck
	npm test --silent

# The same gates as quick. The v1 config still names `make full` as a gate, so the
# target stays until that config is rewritten.
full: quick

# The dev-only TypeScript tools. npm ci runs again only when the manifest or the lock
# file is newer than node_modules.
node_modules: package.json package-lock.json
	npm ci
	touch node_modules
