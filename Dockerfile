FROM python:3.7-buster

COPY ./contribs/docker/certs /usr/share/xivo-certs
RUN true \
    && adduser --quiet --system --group --home /var/lib/wazo-chatd wazo-chatd \
    && mkdir -p /etc/wazo-chatd/conf.d \
    && install -d -o wazo-chatd -g wazo-chatd /run/wazo-chatd/ \
    && install -o wazo-chatd -g wazo-chatd /dev/null /var/log/wazo-chatd.log \
    && apt-get -yqq autoremove \
    && openssl req -x509 -newkey rsa:4096 -keyout /usr/share/xivo-certs/server.key -out /usr/share/xivo-certs/server.crt -nodes -config /usr/share/xivo-certs/openssl.cfg -days 3650 \
    && chown wazo-chatd:wazo-chatd /usr/share/xivo-certs/*

COPY . /usr/src/wazo-chatd
WORKDIR /usr/src/wazo-chatd
RUN true \
  && pip install -r /usr/src/wazo-chatd/requirements.txt \
  && python setup.py install \
  && cp -r etc/* /etc

EXPOSE 9304

CMD ["wazo-chatd"]
