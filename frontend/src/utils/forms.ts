/**
 * react-hook-form emits "" for an untouched optional text/date input rather
 * than omitting the key. FastAPI/Pydantic rejects "" for optional date
 * fields (it's not a valid date, so it can't just be treated as null), so
 * every optional-field payload needs this before it goes over the wire.
 */
export function stripEmptyStrings<T extends object>(payload: T): Partial<T> {
  const result: Partial<T> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (value !== "") {
      (result as Record<string, unknown>)[key] = value;
    }
  }
  return result;
}
