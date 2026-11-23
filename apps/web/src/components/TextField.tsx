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
      <label htmlFor={id} className="block text-sm font-medium">
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
        className={`mt-1 w-full min-w-0 rounded-md border px-3 py-2 font-mono dark:bg-white/5 ${
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
