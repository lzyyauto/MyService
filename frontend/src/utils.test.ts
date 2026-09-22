import { describe, expect, it } from "vitest";
import { formatHours, formatMinutes } from "./utils";

describe("duration formatting", () => {
  it("formats sleep duration stored in hours", () => {
    expect(formatHours(10.5)).toBe("10 小时 30 分");
  });

  it("formats sport duration stored in minutes", () => {
    expect(formatMinutes(92)).toBe("1 小时 32 分");
    expect(formatMinutes(2)).toBe("2 分钟");
  });
});
