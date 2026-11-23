import { FieldError, fieldErrorId } from "./ErrorNotice";

/**
 * Labelled numeric input with a hint and an inline error. `name` should be the
 * request-model field name so API validation errors map straight onto it.
 * The value is kept as a string so partially typed input ("0.", "-") survives.
 */
export function NumberField({
  name,
  label,
  hint,
  value,
  onChange,
  error,
  step = "any",
}: {
  name: string;
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  step?: string;
}) {
  const id = `input-${name}`;
  const hintId = `${id}-hint`;
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        name={name}
        type="number"
        inputMode="decimal"
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={[hint ? hintId : null, error ? fieldErrorId(name) : null].filter(Boolean).join(" ") || undefined}
        className={`mt-1 w-full rounded-md border px-3 py-2 font-mono tabular-nums dark:bg-white/5 ${
          error ? "border-red-500" : "border-black/20 dark:border-white/20"
        }`}
      />
      {hint && (
        <p id={hintId} className="mt-1 text-xs text-black/50 dark:text-white/50">
          {hint}
        </p>
      )}
      <FieldError name={name} message={error} />
    </div>
  );
}
