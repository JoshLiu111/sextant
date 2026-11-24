import temml from "temml";

const cache = new Map<string, string>();

/** LaTeX rendered to native MathML (no web fonts), set in the system math face. */
function toMathML(tex: string): string {
  let html = cache.get(tex);
  if (html === undefined) {
    // Drop Temml's inline `display:block math`, which centres the formula; globals.css sets it inline-left.
    html = temml
      .renderToString(tex, { displayMode: true, annotate: false, throwOnError: true })
      .replace(' class="tml-display" style="display:block math;"', "");
    cache.set(tex, html);
  }
  return html;
}

/** A display formula. `tex` is trusted copy from src/i18n, never user input. */
export function Formula({ tex, className = "" }: { tex: string; className?: string }) {
  return <div className={`formula ${className}`} dangerouslySetInnerHTML={{ __html: toMathML(tex) }} />;
}
