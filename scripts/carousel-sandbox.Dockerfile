FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
# Runtime snapshot contains code, interpreter and dependency closure only.
# OAuth credentials are mounted separately at run time; never copied into images.
COPY runtime/ /home/rodrigo/.hermes/
COPY carousel_hermes_runner.py /opt/buscadin/runner.py
ENV HOME=/state/home HERMES_HOME=/state/profile PYTHONDONTWRITEBYTECODE=1
WORKDIR /tmp
USER 1000:1000
ENTRYPOINT ["/home/rodrigo/.hermes/tools/python-3.14.9+20261021-linux-x64/bin/python3", "-I", "/opt/buscadin/runner.py"]
