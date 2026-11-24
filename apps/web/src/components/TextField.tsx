import { FieldError, fieldErrorId } from "./ErrorNotice";

/**
 * Labelled text or date input with a hint and an inline error; the non-numeric
 * sibling of `NumberField`. `name` should be the request-model field name so API
 * validation errors map straight onto it. Date values are "YYYY-MM-DD" strings.
 */
export function TextField({
  name,
  label,
  hint,
  value,
  onChange,
  error,
  type = "text",
}: {
  name: string;
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  type?: "text" | "date";
}) {
  const id = `input-${name}`;
  const hintId = `${id}-hint`;
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="label">
        {label}
      </label>
      <input
        id={id}
        name={name}
        type={type}
        autoCapitalize={type === "text" ? "characters" : undefined}
        spellCheck={false}
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
