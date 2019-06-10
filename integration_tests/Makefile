.PHONY: test-setup test egg-info pull-images chatd

test-setup: egg-info pull-images chatd db

test:
	pytest -x

egg-info:
	cd .. && python setup.py egg_info

pull-images:
	docker pull rabbitmq
	docker pull wazopbx/wait
	docker pull wazopbx/wazo-auth-mock
	docker pull wazopbx/wazo-confd-mock

chatd:
	docker build --pull -t wazopbx/wazo-chatd ..
	$(MAKE) chatd-test

chatd-test: egg-info
	docker build --no-cache -t wazo-chatd-test -f Dockerfile-chatd ..

db:
	docker build -f ../contribs/docker/Dockerfile-db -t wazopbx/wazo-chatd-db ..
