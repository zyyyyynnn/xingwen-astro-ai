const allowedPublicProtocols = new Set(["http:", "https:"]);

function parsePublicHttpUrl(value: string) {
  try {
    const url = new URL(value);
    if (
      allowedPublicProtocols.has(url.protocol) &&
      !url.username &&
      !url.password
    ) {
      return url.toString();
    }
  } catch {
    // Invalid public configuration falls back to the verified local URL.
  }

  return undefined;
}

export function resolvePublicHttpUrl(
  value: string | undefined,
  fallback: string,
) {
  const safeFallback = parsePublicHttpUrl(fallback);
  if (!safeFallback) {
    throw new Error(
      "The fallback URL must use HTTP or HTTPS without credentials.",
    );
  }

  return (value && parsePublicHttpUrl(value)) || safeFallback;
}
