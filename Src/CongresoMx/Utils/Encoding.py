import httpx


# Decodifica el body de una httpx.Response usando el charset declarado en
# Content-Type. Si no esta declarado, asume iso-8859-1 (default SITL).
# Si la decodificacion estricta falla, fallback a 'replace' para no perder bytes.
def DecodeHttpResponse(Response: httpx.Response) -> tuple[str, str]:
    Body = Response.content
    Declared = Response.charset_encoding or "iso-8859-1"
    try:
        return Body.decode(Declared), Declared
    except UnicodeDecodeError:
        return Body.decode("iso-8859-1", errors="replace"), f"{Declared} (replace)"
