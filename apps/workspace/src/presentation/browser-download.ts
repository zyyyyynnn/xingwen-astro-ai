export function downloadBytes({
  bytes,
  fileName,
  mediaType,
}: {
  readonly bytes: ArrayBuffer;
  readonly fileName: string;
  readonly mediaType: string;
}) {
  const blob = new Blob([bytes], { type: mediaType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}
