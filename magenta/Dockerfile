FROM ubuntu:22.04
ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && apt-get install --no-install-recommends -yq \
    ca-certificates \
    git \
    llvm \
    g++ \
    curl \
    software-properties-common \
    gpg-agent \
    python3-pip
RUN add-apt-repository -y ppa:deadsnakes/ppa
RUN apt-get install -yq python3.8-dev python3.8-full
WORKDIR /root
RUN git clone https://github.com/magenta/magenta -b v2.1.4
WORKDIR /root/magenta
RUN python3.8 -m pip install .
