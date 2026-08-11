/**
 * The source-level data-access package uses the fetch-compatible HeadersInit
 * type, while Node's web-compatible globals do not expose that alias. Keep
 * the adapter's production lib free of DOM declarations and provide only the
 * structural type required to consume the existing repository input types.
 */
type HeadersInit = Headers | Record<string, string> | [string, string][];
