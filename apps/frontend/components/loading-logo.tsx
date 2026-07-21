"use client";

export function LoadingLogo({
  size = 48,
  className = "",
  alt = "Manglar cargando",
}: {
  size?: number;
  className?: string;
  alt?: string;
} = {}) {
  return (
    <span
      className={`relative inline-block shrink-0 ${className}`.trim()}
      style={{ width: size, height: size }}
    >
      {/* Animated mangrove growing — the brand loading animation. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/brand/manglar-loading.webp"
        alt={alt}
        width={size}
        height={size}
        className="manglar-loading-anim block h-full w-full"
      />
      {/* Static isotipo fallback for users who prefer reduced motion. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/brand/manglar-isotipo.png"
        alt={alt}
        width={size}
        height={size}
        className="manglar-loading-static h-full w-full"
      />
    </span>
  );
}
