/** Request-level error (service down, validation summary). Field errors go next to their input instead. */
export function ErrorNotice({ title, message }: { title: string; message: string }) {
  return (
    <div
      role="alert"
      data-testid="error-notice"
      className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100"
    >
      <p className="font-medium">{title}</p>
      <p>{message}</p>
    </div>
  );
}

/** Inline validation message under an input. Pair the input with `aria-describedby={fieldErrorId(name)}`. */
export function FieldError({ name, message }: { name: string; message: string | undefined }) {
  if (!message) return null;
  return (
    <p id={fieldErrorId(name)} data-testid={`field-error-${name}`} className="mt-1 text-sm text-red-700 dark:text-red-400">
      {message}
    </p>
  );
}

export function fieldErrorId(name: string): string {
  return `field-error-${name}`;
}
