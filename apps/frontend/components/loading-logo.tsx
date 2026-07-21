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
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/brand/manglar-isotipo.png"
      alt={alt}
      width={size}
      height={size}
      className={`manglar-isotipo-pulse ${className}`.trim()}
    />
  );
}
