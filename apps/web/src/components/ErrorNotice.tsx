/** Request-level error (service down, validation summary). Field errors go next to their input instead. */
export function ErrorNotice({ title, message }: { title: string; message: string }) {
  return (
    <div
      role="alert"
      data-testid="error-notice"
      className="rounded-card border border-error bg-paper-hi p-3 text-sm text-ink"
    >
      <p className="font-medium text-error">{title}</p>
      <p>{message}</p>
    </div>
  );
}

/** Inline validation message under an input. Pair the input with `aria-describedby={fieldErrorId(name)}`. */
export function FieldError({ name, message }: { name: string; message: string | undefined }) {
  if (!message) return null;
  return (
    <p id={fieldErrorId(name)} data-testid={`field-error-${name}`} className="mt-1 text-sm text-error">
      {message}
    </p>
  );
}

export function fieldErrorId(name: string): string {
  return `field-error-${name}`;
}
