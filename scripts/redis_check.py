#!/usr/bin/env python3
"""Redis Connection Test Script

Validates Redis configuration and connectivity for Django project.
Tests external Redis (non-localhost), raw redis-py connection, and Django cache backend.

Usage:
    # Test using settings from .env
    python scripts/redis_check.py

    # Test specific Redis instance
    python scripts/redis_check.py --host redis.example.com --port 6379

    # Test localhost Redis (override external check)
    python scripts/redis_check.py --host localhost --allow-localhost

    # Test with password
    python scripts/redis_check.py --host redis.example.com --password mypassword

Examples:
    # Use settings from environment
    python scripts/redis_check.py

    # Test production Redis
    python scripts/redis_check.py -H prod-redis.example.com -p 6379

    # Test local Redis for development
    python scripts/redis_check.py -H localhost --allow-localhost

Options:
    -H, --host HOST         Redis host (default: from settings)
    -p, --port PORT         Redis port (default: from settings)
    -P, --password PASS     Redis password (default: from settings)
    --allow-localhost       Allow testing localhost Redis
    --skip-cache            Skip Django cache backend test
    -h, --help              Show this help message
"""
import os
import sys
import time
import socket
import argparse
from urllib.parse import urlparse

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django

django.setup()

from django.conf import settings
from django.core.cache import caches

from utils.text_output import header, info, success, warning, error, section_separator


LOCAL_REDIS_HOSTS = {
    'localhost',
    '127.0.0.1',
    '::1',
}


def _is_local_host(host: str | None) -> bool:
    if not host:
        return True
    return host.strip().lower() in LOCAL_REDIS_HOSTS


def _get_cache_location_host(location: str) -> str | None:
    if not location:
        return None

    parsed = urlparse(location)
    if parsed.scheme in {'redis', 'rediss'}:
        return parsed.hostname

    return None


def assert_external_redis_configured(redis_host: str, allow_localhost: bool) -> None:
    header('Validating Redis configuration')

    info(f"Redis host: {redis_host}")

    if _is_local_host(redis_host):
        if not allow_localhost:
            error(
                "Redis is configured to use a local host. "
                "Use --allow-localhost to test localhost Redis, or provide external host with --host"
            )
            raise SystemExit(2)
        else:
            warning('Testing localhost Redis (allowed by --allow-localhost flag)')

    success('Redis configuration check passed.')
    section_separator()


def test_raw_redis_connection(redis_host: str, redis_port: int, redis_password: str | None) -> None:
    header('Testing raw Redis connection (redis-py)')

    try:
        import redis
    except Exception as exc:
        error(f"Could not import redis library: {exc}")
        raise SystemExit(3)

    header('DNS / TCP diagnostics')
    info(f"Target host: {redis_host}")
    info(f"Target port: {redis_port}")

    resolved = []
    try:
        addrinfos = socket.getaddrinfo(redis_host, redis_port, type=socket.SOCK_STREAM)
        for family, socktype, proto, canonname, sockaddr in addrinfos:
            ip = sockaddr[0]
            if ip not in resolved:
                resolved.append(ip)
        success(f"DNS resolved {len(resolved)} address(es): {', '.join(resolved)}")
    except socket.gaierror as exc:
        error(f"DNS resolution failed (getaddrinfo): {exc}")
        warning('This is usually a local DNS/VPN/proxy/network issue, not a Redis credential issue.')
        section_separator()
        raise SystemExit(4)

    connect_timeout = getattr(settings, 'REDIS_SOCKET_CONNECT_TIMEOUT', 2)
    tcp_ok = False
    for ip in resolved[:5]:
        try:
            start_tcp = time.time()
            with socket.create_connection((ip, int(redis_port)), timeout=connect_timeout):
                elapsed_ms = int((time.time() - start_tcp) * 1000)
                success(f"TCP connect ok: {ip}:{redis_port} ({elapsed_ms}ms)")
                tcp_ok = True
                break
        except OSError as exc:
            warning(f"TCP connect failed: {ip}:{redis_port} ({exc})")

    if not tcp_ok:
        error('TCP connectivity check failed for all resolved IPs. Firewall/VPN/egress rules may be blocking the port.')
        section_separator()
        raise SystemExit(4)

    section_separator()

    start = time.time()
    client = redis.Redis(
        host=redis_host,
        port=redis_port,
        db=0,
        password=redis_password,
        socket_connect_timeout=connect_timeout,
        socket_timeout=getattr(settings, 'REDIS_SOCKET_TIMEOUT', 2),
    )

    try:
        pong = client.ping()
    except Exception as exc:
        error(f"Redis PING failed: {exc}")
        raise SystemExit(4)

    elapsed_ms = int((time.time() - start) * 1000)
    if pong is True:
        success(f"Redis PING ok ({elapsed_ms}ms)")
    else:
        warning(f"Redis PING returned: {pong} ({elapsed_ms}ms)")

    key = f"redis_check:test:{int(time.time())}"
    try:
        client.set(key, 'ok', ex=30)
        value = client.get(key)
        ttl = client.ttl(key)
    except Exception as exc:
        error(f"Redis set/get/ttl failed: {exc}")
        raise SystemExit(5)

    success(f"SET/GET ok. key={key} value={value!r} ttl={ttl}")
    section_separator()


def test_django_cache() -> None:
    header('Testing Django cache backend')

    try:
        cache = caches['default']
    except Exception as exc:
        error(f"Could not access Django default cache: {exc}")
        raise SystemExit(6)

    info(f"Cache backend: {cache.__class__.__module__}.{cache.__class__.__name__}")

    key = f"redis_check:cache:{int(time.time())}"
    try:
        cache.set(key, 'ok', timeout=30)
        value = cache.get(key)
    except Exception as exc:
        error(f"Django cache set/get failed: {exc}")
        raise SystemExit(7)

    if value != 'ok':
        error(f"Django cache returned unexpected value: {value!r}")
        raise SystemExit(8)

    success('Django cache set/get ok.')
    section_separator()


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate Redis configuration and test connectivity.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test using settings from .env
  python scripts/redis_check.py

  # Test specific Redis instance
  python scripts/redis_check.py --host redis.example.com --port 6379

  # Test localhost Redis (for development)
  python scripts/redis_check.py --host localhost --allow-localhost
        """
    )
    parser.add_argument(
        '-H', '--host',
        help='Redis host (default: from settings.REDIS)'
    )
    parser.add_argument(
        '-p', '--port',
        type=int,
        help='Redis port (default: from settings.REDIS)'
    )
    parser.add_argument(
        '-P', '--password',
        help='Redis password (default: from settings.REDIS)'
    )
    parser.add_argument(
        '--allow-localhost',
        action='store_true',
        help='Allow testing localhost Redis (default: external only)'
    )
    parser.add_argument(
        '--skip-cache',
        action='store_true',
        help='Skip Django cache backend test'
    )

    args = parser.parse_args()

    header('Redis Connection Test')
    info('This script validates Redis configuration and runs health checks.')
    section_separator()

    # Get Redis connection details
    redis_config = getattr(settings, 'REDIS', {})
    redis_host = args.host or redis_config.get('host', 'localhost')
    redis_port = args.port or redis_config.get('port', 6379)
    redis_password = args.password if args.password is not None else redis_config.get('pwd')

    # Validate configuration
    assert_external_redis_configured(redis_host, args.allow_localhost)

    # Test raw Redis connection
    test_raw_redis_connection(redis_host, redis_port, redis_password)

    # Test Django cache backend
    if not args.skip_cache:
        test_django_cache()

    success('Redis Connection Test Complete')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()  # New line after ^C
        warning('Cancelled by user.')
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:
        error(f"Unexpected error: {exc}")
        sys.exit(1)
