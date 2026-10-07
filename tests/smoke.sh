#!/usr/bin/env bash
# Smoke-test a built image: start it locked down (read-only rootfs, no capabilities) and probe the
# landing page and every app over HTTP from inside the container, so it works with any Docker setup.
#
#   tests/smoke.sh IMAGE [MANIFEST]
set -euo pipefail

IMAGE=${1:?usage: tests/smoke.sh IMAGE [MANIFEST]}
MANIFEST=${2:-apps.json}
ROOT=/usr/share/nginx/artcraft
NAME="artbox-smoke-$$"
FAILURES=0

cleanup() {
    local status=$?
    if [ "$status" -ne 0 ] || [ "$FAILURES" -ne 0 ]; then docker logs "$NAME" >&2 || true; fi
    docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1" >&2; FAILURES=$((FAILURES + 1)); }
check() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected '$3', got '$2'"; fi; }
check_match() { if [[ "$2" =~ $3 ]]; then pass "$1"; else fail "$1: '$2' does not match /$3/"; fi; }

in_box() { docker exec "$NAME" "$@"; }
# status, content type, content encoding, cache control and location of one request
probe() {
    in_box curl -s -o /dev/null -w '%{http_code}|%{content_type}|%header{content-encoding}|%header{cache-control}|%header{location}' "$@"
}
field() { cut -d'|' -f"$1" <<<"$2"; }

docker run -d --name "$NAME" --read-only --tmpfs /tmp --cap-drop ALL \
    --security-opt no-new-privileges "$IMAGE" >/dev/null

for _ in $(seq 1 50); do
    in_box curl -fs http://127.0.0.1:8080/healthz >/dev/null 2>&1 && break
    sleep 0.2
done

echo "landing page"
check "GET /healthz" "$(in_box curl -s http://127.0.0.1:8080/healthz)" "ok"
r=$(probe http://127.0.0.1:8080/)
check "GET / status" "$(field 1 "$r")" "200"
check_match "GET / type" "$(field 2 "$r")" "^text/html"
check "GET / cache" "$(field 4 "$r")" "no-cache"
check_match "GET / CSP" "$(in_box curl -sI http://127.0.0.1:8080/)" "Content-Security-Policy: default-src 'self'"
r=$(probe -H 'Accept-Encoding: gzip' http://127.0.0.1:8080/assets/style.css)
check "style.css served gzip" "$(field 1 "$r") $(field 3 "$r")" "200 gzip"
check "favicon.ico" "$(field 1 "$(probe http://127.0.0.1:8080/favicon.ico)")" "200"
check "unknown path" "$(field 1 "$(probe http://127.0.0.1:8080/nope/)")" "404"
versions=$(in_box curl -s http://127.0.0.1:8080/versions.json)

home=$(in_box curl -s http://127.0.0.1:8080/)
while IFS=$'\t' read -r id version icon; do
    echo "$id $version"
    check_match "tile links to $id/" "$home" "href=\"$id/\""
    check_match "versions.json lists $id $version" "$versions" "\"version\": \"$version\""
    check "icon" "$(field 1 "$(probe "http://127.0.0.1:8080/$icon")")" "200"

    r=$(probe "http://127.0.0.1:8080/$id")
    check "/$id redirects (relative)" "$(field 1 "$r") $(field 5 "$r")" "301 /$id/"
    r=$(probe "http://127.0.0.1:8080/$id/")
    check "/$id/ status" "$(field 1 "$r")" "200"
    check_match "/$id/ type" "$(field 2 "$r")" "^text/html"
    check "/$id/ cache" "$(field 4 "$r")" "no-cache"

    for hidden in .htaccess _headers deps/ .fingerprint/; do
        check "/$id/$hidden hidden" "$(field 1 "$(probe "http://127.0.0.1:8080/$id/$hidden")")" "404"
    done

    wasm_files=$(in_box find "$ROOT/$id" -name '*.wasm.gz')
    [ -n "$wasm_files" ] || fail "$id: no wasm module in image"
    for gz in $wasm_files; do
        url="http://127.0.0.1:8080${gz#"$ROOT"}"
        url=${url%.gz}
        name=$(basename "$url")
        r=$(probe -H 'Accept-Encoding: gzip' "$url")
        check "$name gzip" "$(field 1 "$r") $(field 2 "$r") $(field 3 "$r")" "200 application/wasm gzip"
        if [[ "$name" =~ -[0-9a-f]{16}_bg\.wasm$ ]]; then expected="public, max-age=31536000, immutable"; else expected="no-cache"; fi
        check "$name cache" "$(field 4 "$r")" "$expected"
        magic=$(in_box sh -c "curl -s '$url' | head -c 4 | od -An -tx1 | tr -d ' \n'")
        check "$name identity (gunzip)" "$magic" "0061736d"
    done
    for js in $(in_box find "$ROOT/$id" -maxdepth 1 -name '*.js.gz' -o -maxdepth 1 -name '*.js'); do
        url="http://127.0.0.1:8080${js#"$ROOT"}"
        url=${url%.gz}
        check_match "$(basename "$url") type" "$(field 2 "$(probe "$url")")" "javascript"
    done
done < <(python3 -c '
import json, sys
for app in json.load(open(sys.argv[1]))["apps"]:
    print(app["id"], app["version"], app["icon"], sep="\t")
' "$MANIFEST")

if [ "$FAILURES" -ne 0 ]; then
    echo "$FAILURES check(s) failed" >&2
    exit 1
fi
echo "all checks passed"
