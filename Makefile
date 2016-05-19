.PHONY: clean clean-build clean-pyc clean-test clean-doc test coverage doc dist install develop

PYTHON=python
PIP=pip

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
	x-www-browser htmlcov/index.html

doc:
	$(MAKE) -C doc html

dist: clean
	$(PYTHON) setup.py sdist
	ls -l dist

install: clean
	$(PYTHON) setup.py install

develop:
	$(PIP) install -r requirements.txt
	$(PIP) install -r optional-requirements.txt
	$(PYTHON) setup.py develop
