.PHONY: setup setup-playwright setup-api setup-web

# Run initial project setup (sync tooling, init git, install hooks)
setup:
	bash scripts/setup.sh

setup-playwright:
	bash scripts/setup.sh playwright

setup-api:
	bash scripts/setup.sh api

setup-web:
	bash scripts/setup.sh web
