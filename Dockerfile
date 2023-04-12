FROM python:3.9-slim-bullseye AS compile-image
LABEL maintainer="Wazo Maintainers <dev@wazo.community>"

RUN python -m venv /opt/venv
# Activate virtual env
ENV PATH="/opt/venv/bin:$PATH"

COPY . /usr/src/wazo-chatd
WORKDIR /usr/src/wazo-chatd
RUN pip install -r requirements.txt
RUN python setup.py install

FROM python:3.9-slim-bullseye AS build-image
COPY --from=compile-image /opt/venv /opt/venv

COPY ./etc/. /etc/
RUN true \
    && adduser --quiet --system --group --home /var/lib/wazo-chatd wazo-chatd \
    && mkdir -p /etc/wazo-chatd/conf.d \
    && install -o wazo-chatd -g wazo-chatd /dev/null /var/log/wazo-chatd.log

EXPOSE 9304

# Activate virtual env
ENV PATH="/opt/venv/bin:$PATH"
CMD ["wazo-chatd"]
