test-smoke:
	.\.conda\python.exe -m pytest tests/test_smoke.py -v

test-edge:
	.\.conda\python.exe -m pytest tests/test_edge_cases.py -v

test-load:
	.\.conda\python.exe -m pytest tests/test_load.py -v

test-errors:
	.\.conda\python.exe -m pytest tests/test_error_scenarios.py -v

test-integration:
	.\.conda\python.exe -m pytest tests/test_integration.py -v -m integration

test-all:
	.\.conda\python.exe -m pytest tests/ -v --ignore=tests/test_integration.py

test-full:
	.\.conda\python.exe -m pytest tests/ -v
