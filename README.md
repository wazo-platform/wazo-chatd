# wazo-chatd

[![Build Status](https://jenkins.wazo.community/buildStatus/icon?job=wazo-chatd)](https://jenkins.wazo.community/job/wazo-chatd)

A microservice to manage message and presence for a [Wazo](http://wazo.community) Engine.

## Docker

The official docker image for this service is `wazoplatform/wazo-chatd`.

### Getting the image

To download the latest image from the docker hub

```sh
docker pull wazoplatform/wazo-chatd
```

### Running wazo-chatd

```sh
docker run wazoplatform/wazo-chatd
```

### Building the image

Building the docker image:

```sh
docker build -t wazoplatform/wazo-chatd .
```
