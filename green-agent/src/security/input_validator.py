"""
Input sanitization middleware for Green Agent.

Validates and sanitizes all external inputs to prevent injection attacks.
Implements Input sanitization for task_ids, benchmarks, URLs, configs.
"""

import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from src.utils.exceptions import SecurityError
from src.benchmarks.constants import SUPPORTED_BENCHMARKS

# Task ID pattern: benchmark.task-name (alphanumeric, hyphens, underscores)
TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]+\.[a-zA-Z0-9_-]+$")

# Safe URL schemes
SAFE_URL_SCHEMES = ["http", "https"]

# Blocked URL schemes (prevent file access, code execution)
BLOCKED_URL_SCHEMES = ["file", "javascript", "data", "vbscript"]


def sanitize_task_id(task_id: str) -> str:
    """
    Sanitize and validate task ID.
    
    Args:
        task_id: Task ID to validate
        
    Returns:
        Sanitized task ID
        
    Raises:
        SecurityError: If task ID is invalid or malicious
    """
    if not task_id or not isinstance(task_id, str):
        raise SecurityError(
            "Task ID must be a non-empty string",
            security_issue="invalid_task_id",
            task_id=str(task_id)
        )

    # Remove leading/trailing whitespace
    task_id = task_id.strip()

    # Check length limits (prevent DoS)
    if len(task_id) > 200:
        raise SecurityError(
            f"Task ID too long: {len(task_id)} characters (max: 200)",
            security_issue="task_id_too_long",
            task_id_length=len(task_id)
        )

    # Validate format
    if not TASK_ID_PATTERN.match(task_id):
        raise SecurityError(
            f"Invalid task ID format: {task_id}. Must match pattern: benchmark.task-name",
            security_issue="invalid_task_id_format",
            task_id=task_id
        )

    return task_id


def sanitize_benchmark(benchmark: str) -> str:
    """
    Sanitize and validate benchmark name.
    
    Args:
        benchmark: Benchmark name to validate
        
    Returns:
        Sanitized benchmark name
        
    Raises:
        SecurityError: If benchmark is invalid or unsupported
    """
    if not benchmark or not isinstance(benchmark, str):
        raise SecurityError(
            "Benchmark must be a non-empty string",
            security_issue="invalid_benchmark",
            benchmark=str(benchmark)
        )

    # Remove leading/trailing whitespace
    benchmark = benchmark.strip().lower()

    # Check against whitelist
    if benchmark not in SUPPORTED_BENCHMARKS:
        raise SecurityError(
            f"Unsupported benchmark: {benchmark}. Supported: {', '.join(SUPPORTED_BENCHMARKS)}",
            security_issue="unsupported_benchmark",
            benchmark=benchmark,
            supported_benchmarks=SUPPORTED_BENCHMARKS
        )

    return benchmark


def sanitize_url(url: str, allow_private_ips: bool = False) -> str:
    """
    Sanitize and validate URL.
    
    Prevents:
    - File access (file://)
    - JavaScript execution (javascript:)
    - SSRF attacks (private IP ranges)
    - Data URI injection (data:)
    
    Args:
        url: URL to validate
        allow_private_ips: Whether to allow private IP addresses
        
    Returns:
        Sanitized URL
        
    Raises:
        SecurityError: If URL is invalid or malicious
    """
    if not url or not isinstance(url, str):
        raise SecurityError(
            "URL must be a non-empty string",
            security_issue="invalid_url",
            url=str(url)
        )

    # Remove leading/trailing whitespace
    url = url.strip()

    # Check length limits
    if len(url) > 2048:
        raise SecurityError(
            f"URL too long: {len(url)} characters (max: 2048)",
            security_issue="url_too_long",
            url_length=len(url)
        )

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SecurityError(
            f"Failed to parse URL: {e}",
            security_issue="url_parse_error",
            url=url
        )

    # Check scheme
    if not parsed.scheme:
        raise SecurityError(
            "URL missing scheme (http:// or https://)",
            security_issue="url_missing_scheme",
            url=url
        )

    scheme = parsed.scheme.lower()

    # Block dangerous schemes
    if scheme in BLOCKED_URL_SCHEMES:
        raise SecurityError(
            f"Blocked URL scheme: {scheme}. Use http:// or https://",
            security_issue="blocked_url_scheme",
            url=url,
            scheme=scheme
        )

    # Require safe schemes
    if scheme not in SAFE_URL_SCHEMES:
        raise SecurityError(
            f"Unsupported URL scheme: {scheme}. Use http:// or https://",
            security_issue="unsupported_url_scheme",
            url=url,
            scheme=scheme
        )

    # Check for private IP addresses (SSRF protection)
    if not allow_private_ips and parsed.hostname:
        if _is_private_ip(parsed.hostname):
            raise SecurityError(
                f"Private IP addresses not allowed: {parsed.hostname}",
                security_issue="private_ip_blocked",
                url=url,
                hostname=parsed.hostname
            )

    return url


def _is_private_ip(hostname: str) -> bool:
    """
    Check if hostname is a private IP address.
    
    Blocks:
    - 127.0.0.0/8 (localhost)
    - 10.0.0.0/8 (private)
    - 172.16.0.0/12 (private)
    - 192.168.0.0/16 (private)
    - 169.254.0.0/16 (link-local)
    - localhost
    
    Args:
        hostname: Hostname to check
        
    Returns:
        True if private IP
    """
    hostname = hostname.lower()

    # Block localhost aliases
    if hostname in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]:
        return True

    # Simple IP range checks (not comprehensive, but sufficient)
    if hostname.startswith("127.") or hostname.startswith("10."):
        return True
    if hostname.startswith("192.168."):
        return True
    if hostname.startswith("169.254."):
        return True

    # 172.16.0.0/12 range
    if hostname.startswith("172."):
        try:
            second_octet = int(hostname.split(".")[1])
            if 16 <= second_octet <= 31:
                return True
        except (IndexError, ValueError):
            pass

    return False


def sanitize_config_value(key: str, value: Any, value_type: type) -> Any:
    """
    Sanitize configuration value.
    
    Args:
        key: Configuration key
        value: Value to sanitize
        value_type: Expected value type
        
    Returns:
        Sanitized value
        
    Raises:
        SecurityError: If value is invalid
    """
    if value is None:
        return None

    # Type check
    if not isinstance(value, value_type):
        try:
            # Attempt type conversion
            value = value_type(value)
        except (TypeError, ValueError) as e:
            raise SecurityError(
                f"Configuration value for '{key}' must be {value_type.__name__}: {e}",
                security_issue="invalid_config_type",
                config_key=key,
                expected_type=value_type.__name__,
                actual_type=type(value).__name__
            )

    # String-specific sanitization
    if isinstance(value, str):
        # Remove control characters
        value = "".join(char for char in value if ord(char) >= 32 or char in ["\n", "\t"])

        # Length limits
        if len(value) > 10000:
            raise SecurityError(
                f"Configuration value for '{key}' too long: {len(value)} characters (max: 10000)",
                security_issue="config_value_too_long",
                config_key=key,
                value_length=len(value)
            )

    return value


def sanitize_dict(data: Dict[str, Any], allowed_keys: Optional[set] = None) -> Dict[str, Any]:
    """
    Sanitize dictionary by removing unexpected keys.
    
    Args:
        data: Dictionary to sanitize
        allowed_keys: Set of allowed keys (None = allow all)
        
    Returns:
        Sanitized dictionary
    """
    if not isinstance(data, dict):
        raise SecurityError(
            "Expected dictionary",
            security_issue="invalid_data_type",
            actual_type=type(data).__name__
        )

    if allowed_keys is None:
        return data

    # Remove unexpected keys
    sanitized = {k: v for k, v in data.items() if k in allowed_keys}

    return sanitized


__all__ = [
    "sanitize_task_id",
    "sanitize_benchmark",
    "sanitize_url",
    "sanitize_config_value",
    "sanitize_dict",
    "SUPPORTED_BENCHMARKS",
]
