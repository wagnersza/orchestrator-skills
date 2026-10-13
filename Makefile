# The gates: the TypeScript typecheck, then the node --test suite.

.PHONY: quick full

quick: node_modules
	npm run --silent typecheck
	npm test --silent

# The whole-repo gate a worker runs before its push. The suite is fast, so it is quick.
full: quick

# The dev-only TypeScript tools. npm ci runs again only when the manifest or the lock
# file is newer than node_modules.
node_modules: package.json package-lock.json
	npm ci
	touch node_modules
