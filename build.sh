#!/bin/sh

set -e

sudo apt-get update && \
  sudo apt-get install python3-dev && \
  sudo pip3 install -U pip && \
  sudo pip3 install -U setuptools && \
  sudo pip3 install -U -r requirements.txt
