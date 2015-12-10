.PHONY: clean-pyc clean-build clean docs test coverage

clean: clean-build clean-pyc clean-test

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -rf {} +

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/

test:
	py.test test

coverage:
	py.test --cov=tabun_api --cov-report html test
	x-www-browser htmlcov/index.html

dist: clean
	python setup.py sdist
	ls -l dist

install: clean
	python setup.py install

develop:
	pip install -r requirements.txt
	python setup.py develop
