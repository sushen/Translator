"""Use native certificate trust on Windows without disabling TLS verification."""
import ssl
import sys
import httpx


def verified_http_client():
    if sys.platform == "win32":
        import truststore
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    else:
        context = ssl.create_default_context()
    return httpx.Client(verify=context, timeout=120.0, follow_redirects=False)
