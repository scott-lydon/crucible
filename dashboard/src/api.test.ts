import { describe, it, expect } from "vitest"
import { isNotMeasured } from "./api"

describe("isNotMeasured", () => {
  it("detects the empty state", () => {
    expect(isNotMeasured({ status: "Not yet measured" })).toBe(true)
    expect(
      isNotMeasured({
        per_round: [],
        baseline_validation_detection: null,
        gap: null,
        white_box: null,
        dollars_per_caught_hack: null,
        human_minutes_per_1k_outputs: null,
      }),
    ).toBe(false)
  })
})
