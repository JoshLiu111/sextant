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
      <label htmlFor={id} className="label">
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
        className="field mt-1"
      />
      {hint && (
        <p id={hintId} className="hint mt-1">
          {hint}
        </p>
      )}
      <FieldError name={name} message={error} />
    </div>
  );
}
