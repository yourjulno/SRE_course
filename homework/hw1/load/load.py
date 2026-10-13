#!/usr/bin/env python3
"""Continuous open-loop HTTP load with 1s timeout and per-request CSV evidence."""
import argparse
import collections
import concurrent.futures
import csv
import json
import time
import urllib.error
import urllib.request


def request(seq, target, timeout):
    start = time.time()
    kind, version, pod, status = 'other', '', '', 0
    try:
        with urllib.request.urlopen(target, timeout=timeout) as response:
            status = response.status
            data = json.loads(response.read())
            version, pod = data.get('version', ''), data.get('pod', '')
            kind = 'ok' if 200 <= status < 400 else 'http_error'
    except urllib.error.HTTPError as exc:
        status = exc.code
        kind = '5xx' if status >= 500 else '4xx'
    except Exception as exc:
        import socket
        import errno
        if isinstance(exc, (TimeoutError, socket.timeout)) or 'timed out' in str(exc).lower():
            kind = 'timeout'
        elif isinstance(exc, (ConnectionRefusedError, ConnectionResetError)) or isinstance(exc, urllib.error.URLError) and ('refused' in str(exc).lower() or 'reset' in str(exc).lower()):
            kind = 'connection_error'
        else:
            kind = type(exc).__name__
    return {'id': seq, 'timestamp': round(start, 3), 'latency_ms': round((time.time()-start)*1000, 2),
            'kind': kind, 'status': status, 'version': version, 'pod': pod}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', default='http://127.0.0.1:8080/')
    p.add_argument('--rps', type=float, default=15)
    p.add_argument('--duration', type=float, default=90)
    p.add_argument('--timeout', type=float, default=1.5)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    if args.rps < 10 or args.duration <= 0 or not 0 < args.timeout <= 2:
        p.error('rps must be >= 10, duration positive, timeout <= 2s')
    start = time.monotonic()
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(20, int(args.rps * args.timeout * 3))) as pool:
        seq = 0
        while True:
            scheduled = start + seq / args.rps
            if scheduled >= start + args.duration:
                break
            remaining = scheduled - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            futures.append(pool.submit(request, seq, args.url, args.timeout))
            seq += 1
        rows = [future.result() for future in futures]
    rows.sort(key=lambda row: row['id'])
    with open(args.output, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'timestamp', 'latency_ms', 'kind', 'status', 'version', 'pod'])
        writer.writeheader()
        writer.writerows(rows)
    counts = collections.Counter(r['kind'] for r in rows)
    versions = collections.Counter(r['version'] for r in rows if r['version'])
    pods = collections.Counter(r['pod'] for r in rows if r['pod'])
    print(json.dumps({'total': len(rows), 'errors': sum(n for k, n in counts.items() if k != 'ok'),
                      'kinds': counts, 'versions': versions, 'pods': pods,
                      'csv': args.output}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
