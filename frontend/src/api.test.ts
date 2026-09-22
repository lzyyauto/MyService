import { describe, expect, it } from "vitest";
import { normalizeApiKey } from "./api";

describe("normalizeApiKey", () => {
  it.each([
    ["plain-api-key", "plain-api-key"],
    ["  Bearer plain-api-key  ", "plain-api-key"],
    ["Authorization: Bearer plain-api-key", "plain-api-key"],
    ["authorization: bearer plain-api-key", "plain-api-key"],
  ])("normalizes %s", (input, expected) => {
    expect(normalizeApiKey(input)).toBe(expected);
  });
});
