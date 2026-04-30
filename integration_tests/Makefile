test-setup: egg-info microsoft-mock chatd chatd-test chatd-connectors-test connector-mock-test db

test:
	pytest -x

egg-info:
	cd .. && python setup.py egg_info

microsoft-mock:
	docker build --no-cache -t microsoft-graphql-mock -f docker/Dockerfile-microsoft-mock ..

chatd:
	docker build -t wazoplatform/wazo-chatd ..

chatd-test: egg-info
	docker build --no-cache -t wazo-chatd-test -f Dockerfile-chatd ..

chatd-connectors-test: chatd-test
	docker build --no-cache -t wazo-chatd-connectors-test -f docker/Dockerfile-chatd-connectors .

connector-mock-test:
	docker build --no-cache -t connector-mock-test -f docker/Dockerfile-connector-mock .

db:
	docker build -f ../contribs/docker/Dockerfile-db -t wazoplatform/wazo-chatd-db ..

.PHONY: test-setup test egg-info chatd chatd-test chatd-connectors-test connector-mock-test db
