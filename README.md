wazo-chatd
==========

[![Build Status](https://jenkins.wazo.community/buildStatus/icon?job=wazo-chatd)](https://jenkins.wazo.community/job/wazo-chatd)

A micro service to manage message and presence for a [Wazo](http://wazo.community) Engine.


## Docker

The official docker image for this service is `wazopbx/wazo-chatd`.


### Getting the image

To download the latest image from the docker hub

```sh
docker pull wazopbx/wazo-chatd
```


### Running wazo-chatd

```sh
docker run wazopbx/wazo-chatd
```

### Building the image

Building the docker image:

```sh
docker build -t wazopbx/wazo-chatd .
```

