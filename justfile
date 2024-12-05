version := `python3 -c "from src.LumixG9IIRemoteControl import __version__; print(__version__)"`

default:
	@echo "\"just publish\"?"

publish:
	@if [ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]; then exit 1; fi
	gh release create "v{{version}}"
	flit publish

clean:
	@find . | grep -E "(__pycache__|\.pyc|\.pyo$)" | xargs rm -rf
	@rm -rf src/*.egg-info/ build/ dist/ .tox/ ./doc/_build/

format:
	isort src
	black src
	blacken-docs README.md

lint:
	black --check src
	pflake8 src