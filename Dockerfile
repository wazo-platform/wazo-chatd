FROM python:3.7-slim-buster AS compile-image


RUN python -m venv /opt/venv
# Activate virtual env
ENV PATH="/opt/venv/bin:$PATH"

COPY . /usr/src/wazo-chatd
WORKDIR /usr/src/wazo-chatd
RUN pip install -r requirements.txt
RUN python setup.py install

FROM python:3.7-slim AS build-image
COPY --from=compile-image /opt/venv /opt/venv

COPY ./etc/. /etc/
COPY ./contribs/docker/certs /usr/share/xivo-certs
RUN true \
    && adduser --quiet --system --group --home /var/lib/wazo-chatd wazo-chatd \
    && mkdir -p /etc/wazo-chatd/conf.d \
    && install -d -o wazo-chatd -g wazo-chatd /run/wazo-chatd/ \
    && install -o wazo-chatd -g wazo-chatd /dev/null /var/log/wazo-chatd.log \
    && openssl req -x509 -newkey rsa:4096 -keyout /usr/share/xivo-certs/server.key -out /usr/share/xivo-certs/server.crt -nodes -config /usr/share/xivo-certs/openssl.cfg -days 3650 \
    && chown wazo-chatd:wazo-chatd /usr/share/xivo-certs/*

EXPOSE 9304

# Activate virtual env
ENV PATH="/opt/venv/bin:$PATH"
CMD ["wazo-chatd"]
