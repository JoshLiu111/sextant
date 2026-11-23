import { en, type Messages } from "./en";

// Single locale for now. When i18n lands, resolve the locale here
// (e.g. from a route segment) and return the matching dictionary.
export function getMessages(): Messages {
  return en;
}

export type { Messages };
