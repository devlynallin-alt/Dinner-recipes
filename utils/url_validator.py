"""
SSRF Protection Module

Validates URLs before making HTTP requests to prevent Server-Side Request Forgery attacks.
Blocks access to localhost, private IPs, and non-http(s) schemes.
"""

import ipaddress
import socket
from urllib.parse import urlparse
import requests


class SSRFError(Exception):
    """Raised when a URL fails SSRF validation."""
    pass


def is_private_ip(ip_str):
    """Check if an IP address is private, loopback, or otherwise internal."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private or
            ip.is_loopback or
            ip.is_reserved or
            ip.is_link_local or
            ip.is_multicast or
            # Explicit checks for common internal ranges
            ip_str.startswith('127.') or
            ip_str.startswith('10.') or
            ip_str.startswith('192.168.') or
            ip_str.startswith('172.16.') or
            ip_str.startswith('172.17.') or
            ip_str.startswith('172.18.') or
            ip_str.startswith('172.19.') or
            ip_str.startswith('172.20.') or
            ip_str.startswith('172.21.') or
            ip_str.startswith('172.22.') or
            ip_str.startswith('172.23.') or
            ip_str.startswith('172.24.') or
            ip_str.startswith('172.25.') or
            ip_str.startswith('172.26.') or
            ip_str.startswith('172.27.') or
            ip_str.startswith('172.28.') or
            ip_str.startswith('172.29.') or
            ip_str.startswith('172.30.') or
            ip_str.startswith('172.31.') or
            ip_str == '::1' or
            ip_str == '0.0.0.0'
        )
    except ValueError:
        return True  # Invalid IP, treat as unsafe


def is_safe_url(url):
    """
    Validate that a URL is safe to fetch.

    Returns (is_safe, error_message) tuple.

    Checks:
    - Scheme is http or https only
    - Host resolves to a public IP (not private/loopback)
    - Not targeting localhost or internal services
    """
    if not url:
        return False, "Empty URL"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    # Check scheme
    if parsed.scheme not in ('http', 'https'):
        return False, f"Invalid scheme: {parsed.scheme}. Only http and https are allowed."

    # Check for empty host
    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    # Check for common localhost aliases
    localhost_aliases = {
        'localhost', 'localhost.localdomain',
        '127.0.0.1', '::1', '0.0.0.0',
        '[::1]', '[0:0:0:0:0:0:0:1]'
    }
    if hostname.lower() in localhost_aliases:
        return False, "Cannot access localhost"

    # Check for IP addresses directly in URL
    try:
        ip = ipaddress.ip_address(hostname)
        if is_private_ip(str(ip)):
            return False, f"Cannot access private/internal IP: {hostname}"
    except ValueError:
        # Not an IP address, resolve hostname
        pass

    # Resolve hostname and check resolved IPs
    try:
        # Get all IPs the hostname resolves to
        resolved_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)

        for family, socktype, proto, canonname, sockaddr in resolved_ips:
            ip_str = sockaddr[0]
            if is_private_ip(ip_str):
                return False, f"Hostname resolves to private/internal IP: {ip_str}"
    except socket.gaierror as e:
        return False, f"Cannot resolve hostname: {hostname}"

    return True, None


def safe_fetch(url, headers=None, timeout=10, max_size=10*1024*1024, stream=False):
    """
    Fetch a URL with SSRF protection and size limits.

    Args:
        url: The URL to fetch
        headers: Optional HTTP headers dict
        timeout: Request timeout in seconds (default 10)
        max_size: Maximum response size in bytes (default 10MB)
        stream: Whether to return the response in streaming mode

    Returns:
        requests.Response object

    Raises:
        SSRFError: If the URL fails security validation
        requests.RequestException: For network errors
    """
    # Validate URL
    is_safe, error = is_safe_url(url)
    if not is_safe:
        raise SSRFError(error)

    # Default headers if not provided
    if headers is None:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # Make request with streaming to check size
    response = requests.get(url, headers=headers, timeout=timeout, stream=True)
    response.raise_for_status()

    # Check content-length header if available
    content_length = response.headers.get('content-length')
    if content_length and int(content_length) > max_size:
        response.close()
        raise SSRFError(f"Response too large: {content_length} bytes (max {max_size})")

    if stream:
        return response

    # Read content with size limit
    content = b''
    for chunk in response.iter_content(chunk_size=8192):
        content += chunk
        if len(content) > max_size:
            response.close()
            raise SSRFError(f"Response exceeded maximum size of {max_size} bytes")

    # Replace content in response for non-streaming use
    response._content = content
    return response
