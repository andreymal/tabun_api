.PHONY: clean clean-build clean-pyc clean-test clean-doc test coverage doc dist install develop

PYTHON?=python
PIP?=pip

help:
	@echo "tabun_api"
	@echo
	@echo "clean - remove all build, test, coverage, doc and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "clean-doc - remove Sphinx builds and artifacts"
	@echo "test - run tests quickly with the default Python with pytest"
	@echo "coverage - check code coverage quickly with the default Python and pytest"
	@echo "doc - generate Sphinx HTML documentation"
	@echo "dist - package"
	@echo "install - install the package to the active Python's site-packages"
	@echo "develop - install the package for development as editable"

clean: clean-build clean-pyc clean-test clean-doc

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	rm -fr *.egg-info
	rm -fr *.egg

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test:
	rm -f .coverage
	rm -fr htmlcov/

clean-doc:
	rm -fr doc/build
	rm -fr doc/source/.buildinfo

test:
	py.test test

coverage:
	py.test --cov=tabun_api --cov-report html test
	ls -lh htmlcov/index.html

doc:
	$(MAKE) -C doc html

dist: clean
	$(PYTHON) setup.py sdist
	ls -l dist

install: clean
	$(PIP) install .

develop:
	$(PIP) install -r requirements.txt -r optional-requirements.txt -r dev-requirements.txt
	$(PIP) install -e .
