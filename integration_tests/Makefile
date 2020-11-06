test-setup: egg-info chatd chatd-test db

test:
	pytest -x

egg-info:
	docker pull wazoplatform/pull-test
	cd .. && python setup.py egg_info

chatd:
	docker build -t wazoplatform/wazo-chatd ..

chatd-test: egg-info
	docker build --no-cache -t wazo-chatd-test -f Dockerfile-chatd ..

db:
	docker build -f ../contribs/docker/Dockerfile-db -t wazoplatform/wazo-chatd-db ..

.PHONY: test-setup test egg-info chatd chatd-test
