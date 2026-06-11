#!/usr/bin/env sh
set -eu

print_header() {
    printf '%-20s | %-12s | %-12s | %-12s\n' "Metric" "last-7d" "last-30d" "all-time"
    printf '%-20s-+-%-12s-+-%-12s-+-%-12s\n' "--------------------" "------------" "------------" "------------"
}

fixture_value() {
    metric="$1"
    bucket="$2"
    python3 - "$metric" "$bucket" <<'PY'
import json
import os
import sys

metric, bucket = sys.argv[1], sys.argv[2]
data = json.loads(os.environ["KPI_FIXTURE_JSON"])
print(data.get(metric, {}).get(bucket, "not configured"))
PY
}

query_value() {
    metric="$1"
    bucket="$2"
    if [ -n "${KPI_FIXTURE_JSON:-}" ]; then
        fixture_value "$metric" "$bucket"
        return
    fi
    if [ -n "${KPI_QUERY_CMD:-}" ]; then
        sh -c "$KPI_QUERY_CMD \"\$1\" \"\$2\"" sh "$metric" "$bucket"
        return
    fi
    if [ -n "${CF_ACCOUNT_ID:-}" ] && [ -n "${CF_API_TOKEN:-}" ]; then
        printf 'not configured (analytics query command missing)'
        return
    fi
    printf 'not configured'
}

row_value() {
    metric="$1"
    bucket="$2"
    if [ "$metric" = "C1" ] && [ "${LICENSE_TELEMETRY_DEPLOYED:-0}" != "1" ]; then
        printf 'n/a (license telemetry not deployed)'
        return
    fi
    query_value "$metric" "$bucket"
}

print_row() {
    metric="$1"
    label="$2"
    last_7d="$(row_value "$metric" "last_7d")"
    last_30d="$(row_value "$metric" "last_30d")"
    all_time="$(row_value "$metric" "all_time")"
    printf '%-20s | %-12s | %-12s | %-12s\n' "$label" "$last_7d" "$last_30d" "$all_time"
}

printf 'Atlas KPI snapshot\n'
printf 'Date ranges: last-7d, last-30d, all-time\n\n'
print_header
print_row "A1" "A1 installs"
print_row "A3" "A3 weekly actives"
print_row "AC1" "AC1 reach_execute"
print_row "AC2" "AC2 ship_check_ok"
print_row "C1" "C1 conversion"
