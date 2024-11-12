.PHONY: test test-cov test-html clean

test:
	pytest -v

test-cov:
	pytest --cov=. --cov-report=term-missing

test-html:
	pytest --cov=. --cov-report=html

clean:
	rm -rf .coverage htmlcov .pytest_cache __pycache__
