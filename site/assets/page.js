// The apps need a secure context (HTTPS or localhost) for WebGPU, browser file storage and the clipboard.
if (!window.isSecureContext) {
  document.getElementById("insecure-notice").hidden = false;
}
