"use client";

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

export const APK_PATH = "/downloads/telemetry-agent.apk";

/** Absolute download link for the phone camera, on whatever hosts this page. */
export function apkDownloadUrl(origin: string): string {
  return `${origin.replace(/\/$/, "")}${APK_PATH}`;
}

/** Scannable APK link. Mount-gated: the origin only exists in the browser. */
export default function ApkQr() {
  const [url, setUrl] = useState("");
  useEffect(() => {
    setUrl(apkDownloadUrl(window.location.origin));
  }, []);
  if (!url) {
    return (
      <span
        aria-hidden
        className="block h-[120px] w-[120px] rounded-md bg-surface-2"
      />
    );
  }
  return (
    <QRCodeSVG
      value={url}
      size={120}
      aria-label={`QR code: download the Android app from ${url}`}
    />
  );
}
