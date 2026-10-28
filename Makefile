.PHONY: install run test
install:
	pip install -r requirements.txt
run:
	python run_pipeline.py
test:
	pytest -q
