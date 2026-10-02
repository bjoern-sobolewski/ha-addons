#!/bin/sh
set -eu
umask 077
exec python3 /opt/ha/bootstrap.py
