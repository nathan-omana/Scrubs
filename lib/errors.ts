// Errors shared by the real client and the mock, so both show the same text.

export type ApiErrorKind = "network" | "timeout" | "locked" | "blocked" | "gemini" | "not_found" | "server";

export class ApiError extends Error {
  constructor(
    public kind: ApiErrorKind,
    message: string,
    public status?: number,
    public identifierCount?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const LOCKED_MSG = "HIGH items are always masked and can't be unmasked.";

export const errorText = (e: unknown, fallback = "Something went wrong.") =>
  e instanceof Error && e.message ? e.message : fallback;
