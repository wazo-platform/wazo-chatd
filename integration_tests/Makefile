test-setup: egg-info microsoft-mock chatd chatd-test db

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

db:
	docker build -f ../contribs/docker/Dockerfile-db -t wazoplatform/wazo-chatd-db ..

.PHONY: test-setup test egg-info chatd chatd-test
