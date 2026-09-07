import { fmtDate, fmtDatetime } from "@/lib/format"

describe("fmtDate", () => {
  it("renders a UTC noon timestamp in CAT (same calendar day)", () => {
    // 2026-09-07T12:00Z = 2026-09-07T14:00 CAT — still 07 Sep
    // Use regex: Node ICU may output "Sept" vs "Sep" depending on version
    expect(fmtDate("2026-09-07T12:00:00Z")).toMatch(/^07 Sept? 2026$/)
  })

  it("crosses a calendar day boundary: 23:30 UTC is 01:30 CAT next day", () => {
    // 2026-09-07T23:30Z = 2026-09-08T01:30 CAT — must show 08, not 07
    expect(fmtDate("2026-09-07T23:30:00Z")).toMatch(/^08 Sept? 2026$/)
  })
})

describe("fmtDatetime", () => {
  it("formats date and time in CAT", () => {
    // 2026-09-07T06:00Z = 2026-09-07T08:00 CAT
    expect(fmtDatetime("2026-09-07T06:00:00Z")).toMatch(/^07 Sept? 2026,\s*08:00$/)
  })

  it("crosses midnight: 22:30 UTC is 00:30 CAT next day", () => {
    // 2026-09-07T22:30Z = 2026-09-08T00:30 CAT — must show 08, not 07
    expect(fmtDatetime("2026-09-07T22:30:00Z")).toMatch(/^08 Sept? 2026,\s*00:30$/)
  })
})
