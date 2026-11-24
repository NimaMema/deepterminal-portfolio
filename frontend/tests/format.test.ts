import { formLabel, money, num, pct, price, signedPct } from "@/lib/format";

describe("format", () => {
  it("formats millions and billions", () => {
    expect(money(950)).toBe("$950m");
    expect(money(17146.5)).toBe("$17.1bn");
    expect(money(-11000)).toBe("−$11bn");
  });
  it("never fabricates a number for missing values", () => {
    for (const f of [money, num, pct, price, signedPct]) expect(f(null as unknown as number)).toBe("—");
    expect(pct(Number.NaN)).toBe("—");
  });
  it("formats percentages and signs", () => {
    expect(pct(0.1234)).toBe("12.3%");
    expect(pct(-0.05)).toBe("−5.0%");
    expect(signedPct(0.2)).toBe("+20.0%");
    expect(price(140)).toBe("$140.00");
  });
});

describe("formLabel", () => {
  it("names common SEC forms and falls back to the form code", () => {
    expect(formLabel("10-Q")).toBe("Quarterly report");
    expect(formLabel("DEF 14A")).toBe("Proxy statement");
    expect(formLabel("N-CSR")).toBe("Form N-CSR");
  });
});
