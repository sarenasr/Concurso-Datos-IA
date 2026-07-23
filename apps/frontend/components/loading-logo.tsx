"use client";

export function LoadingLogo({
  size = 80,
  responsive = false,
  className = "",
  alt = "Manglar cargando",
}: {
  size?: number;
  /** Grow the logo on larger viewports instead of staying fixed at `size`. */
  responsive?: boolean;
  className?: string;
  alt?: string;
} = {}) {
  return (
    <span
      className={`flex items-center justify-center shrink-0 ${
        responsive ? "manglar-loading-responsive" : ""
      } ${className}`.trim()}
      style={responsive ? undefined : { width: size, height: size }}
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
