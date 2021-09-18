#!/bin/bash


if [[ $2 == "up" ]]; then
  docker-compose -f ../ir/$1.app.yaml -p app --env-file ./env up -d
else
  docker-compose -f ../ir/$1.app.yaml -p app --env-file ./env down -t 1
fi
