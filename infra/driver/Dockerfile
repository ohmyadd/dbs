ARG IMAGE_REPO=ohmy

FROM $IMAGE_REPO/python3_base:1.0.0

RUN pip3 install flask netaddr ovsdbapp pyroute2

RUN rm -rf /var/run /run && mkdir /var/run && \
    echo 'echo "tcp://127.0.0.1:8089" > /etc/docker/plugins/ovn.spec' > /conf.sh && \
    chmod a+x /conf.sh

ADD main.py /src/
