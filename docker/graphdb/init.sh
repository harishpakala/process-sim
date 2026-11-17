#!/bin/sh
set -eu

base="http://graphdb:7200"
echo "Waiting for GraphDB REST API..."
attempt=0
until curl --silent --fail --output /dev/null "$base/rest/repositories"; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "GraphDB did not become ready within 180 seconds" >&2
    exit 1
  fi
  sleep 3
done

echo "Checking AAST repository..."
status=$(curl --silent --output /dev/null --write-out '%{http_code}' "$base/repositories/AAST")
if [ "$status" = "200" ]; then
  echo "AAST repository already exists; leaving it unchanged."
elif [ "$status" = "404" ]; then
  echo "Creating AAST repository..."
  curl --fail --show-error --silent --request POST \
    --form "config=@/config/AAST.ttl;type=text/turtle" \
    "$base/rest/repositories"
  echo
else
  echo "Unexpected AAST repository response: HTTP $status" >&2
  exit 1
fi

echo "Verifying AAST SPARQL endpoint..."
curl --fail --show-error --silent --get \
  --data-urlencode 'query=ASK { ?s ?p ?o }' \
  --header 'Accept: application/sparql-results+json' \
  "$base/repositories/AAST" >/dev/null
echo "AAST repository is ready (RDF import is a separate step)."
