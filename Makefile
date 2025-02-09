.PHONY: help docs
# Put it first so that "make" without argument is like "make help"
# God bless the interwebs:
# https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
help: ## List Makefile targets
	$(info Makefile documentation)
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-10s\033[0m %s\n", $$1, $$2}'

clean: ## Clean generated files
	rm -rf dist/

lint: ## Run code quality tools
	poetry run isort python_bundler
	poetry run black python_bundler
	poetry run mypy python_bundler
	poetry run pylint python_bundler

build: ## Build python dist
	poetry build

upload: ## Upload python dist
	echo "Please run 'twine upload' manually."
