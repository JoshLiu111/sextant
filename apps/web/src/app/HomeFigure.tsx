import Image from "next/image";

/**
 * A capture of one of the tools' own screens, light and dark, following the
 * page's theme (`<html data-theme>`). Files live in /public/landing as `<name>.png` and
 * `<name>-dark.png`; `.hallmark/capture-landing.mjs` retakes them.
 */
export function ProductPicture({
  name,
  width,
  height,
  alt,
  priority = false,
  sizes = "(min-width: 64rem) 58vw, 100vw",
}: {
  name: string;
  width: number;
  height: number;
  alt: string;
  priority?: boolean;
  sizes?: string;
}) {
  // Both modes are in the markup; CSS shows the one matching <html data-theme>.
  // The hidden one is lazy, so it only loads once its theme is switched on.
  const common = { width, height, sizes } as const;
  return (
    <>
      <Image {...common} alt={alt} priority={priority} src={`/landing/${name}.png`} className="pic-light h-auto w-full" />
      <Image {...common} alt={alt} src={`/landing/${name}-dark.png`} className="pic-dark h-auto w-full" />
    </>
  );
}

/** A product capture on a printed sheet, crop-marked like a proof. */
export function HomeFigure({
  name,
  width,
  height,
  alt,
  caption,
  priority = false,
  className = "",
  children,
  overlay,
}: {
  /** File stem in /public/landing: `<name>.png` and `<name>-dark.png`. */
  name: string;
  width: number;
  height: number;
  alt: string;
  caption?: string;
  priority?: boolean;
  className?: string;
  /** Drawn around the sheet, e.g. guides along its edges. */
  children?: React.ReactNode;
  /** Drawn over the picture itself, positioned in % of the capture. */
  overlay?: React.ReactNode;
}) {
  return (
    <figure className={`min-w-0 ${className}`}>
      <div className="crop relative">
        <div data-slot={name} data-kind="product" className="sheet">
          <div className="relative">
            <ProductPicture name={name} width={width} height={height} alt={alt} priority={priority} />
            {overlay}
          </div>
        </div>
        {children}
      </div>
      {caption && <figcaption className="mt-4 text-sm text-muted">{caption}</figcaption>}
    </figure>
  );
}
