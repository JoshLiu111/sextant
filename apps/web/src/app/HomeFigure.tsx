import { getImageProps } from "next/image";

/**
 * A capture of one of the tools' own screens, light and dark, following the
 * visitor's colour scheme. Files live in /public/landing as `<name>.png` and
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
  const common = { alt, width, height, priority, sizes } as const;
  const { props: light } = getImageProps({ ...common, src: `/landing/${name}.png` });
  const {
    props: { srcSet: darkSrcSet },
  } = getImageProps({ ...common, src: `/landing/${name}-dark.png` });
  return (
    <picture>
      <source media="(prefers-color-scheme: dark)" srcSet={darkSrcSet} />
      {/* eslint-disable-next-line jsx-a11y/alt-text -- alt is in the spread props */}
      <img {...light} className="block h-auto w-full" />
    </picture>
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
