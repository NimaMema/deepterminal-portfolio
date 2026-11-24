"use client";

import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { isNum, num, pct, price } from "@/lib/format";

// SVG presentation attributes cannot resolve CSS variables, so chart colours are literal (same values as the theme tokens).
export const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"];
const C = { grid: "#1b2431", axis: "#263243", tick: "#8593a6", zero: "#3a4a60", label: "#b6c2d1", s2: "#d95926" };
const AXIS = { stroke: "#263243", tick: { fill: "#8593a6", fontSize: 11 }, tickLine: false };

function TT({ active, payload, label, fmt }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string; fmt: (v: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-ink-600 bg-ink-900/95 px-2.5 py-1.5 text-xs shadow-xl">
      <div className="mb-0.5 font-medium text-fg">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2 text-fg-2">
          <span className="size-2 rounded-sm" style={{ background: p.color }} aria-hidden />{p.name}
          <span className="num ml-auto pl-3 text-fg">{isNum(p.value) ? fmt(p.value) : "—"}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-fg-3">
      {items.map((i) => <span key={i.label} className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: i.color }} aria-hidden />{i.label}</span>)}
    </div>
  );
}

export function BarTrend<T extends Record<string, unknown>>({ data, x, y, label, fmt = (v) => num(v), height = 200, color = SERIES[0], highlightNegative }:
  { data: T[]; x: keyof T; y: keyof T; label: string; fmt?: (v: number) => string; height?: number; color?: string; highlightNegative?: boolean }) {
  return (
    <div role="img" aria-label={`${label} bar chart`}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={C.grid} strokeDasharray="0" />
          <XAxis dataKey={x as string} {...AXIS} />
          <YAxis {...AXIS} width={56} tickFormatter={(v) => fmt(v)} />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<TT fmt={fmt} />} />
          <ReferenceLine y={0} stroke={C.zero} />
          <Bar isAnimationActive={false} dataKey={y as string} name={label} radius={[4, 4, 0, 0]} maxBarSize={34}>
            {data.map((d, i) => <Cell key={i} fill={highlightNegative && (d[y] as number) < 0 ? C.s2 : color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LineTrend<T extends Record<string, unknown>>({ data, x, series, fmt = (v) => pct(v), height = 200, refY }:
  { data: T[]; x: keyof T; series: { key: keyof T; label: string; color?: string; dashed?: boolean }[]; fmt?: (v: number) => string; height?: number; refY?: { y: number; label: string } }) {
  return (
    <div role="img" aria-label={`${series.map((s) => s.label).join(", ")} line chart`}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={C.grid} />
          <XAxis dataKey={x as string} {...AXIS} />
          <YAxis {...AXIS} width={56} tickFormatter={(v) => fmt(v)} domain={["auto", "auto"]} />
          <Tooltip content={<TT fmt={fmt} />} cursor={{ stroke: C.zero }} />
          {refY && <ReferenceLine y={refY.y} stroke={C.s2} strokeDasharray="5 4" label={{ value: refY.label, fill: C.label, fontSize: 11, position: "insideTopRight" }} />}
          {series.map((s, i) => (
            <Line isAnimationActive={false} key={String(s.key)} dataKey={s.key as string} name={s.label} stroke={s.color ?? SERIES[i]} strokeWidth={2}
              strokeDasharray={s.dashed ? "5 4" : undefined} dot={{ r: 3, strokeWidth: 0, fill: s.color ?? SERIES[i] }} activeDot={{ r: 5 }} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
      {series.length > 1 && <Legend items={series.map((s, i) => ({ label: s.label, color: s.color ?? SERIES[i] }))} />}
    </div>
  );
}

/** Diverging heatmap: value relative to a reference (e.g. current price). Blue above, red below, grey ≈ equal. */
export function Heatmap({ rows, cols, values, rowLabel, colLabel, reference, fmt = (v) => price(v), rowFmt = (v) => pct(v), colFmt = (v) => pct(v) }:
  { rows: number[]; cols: number[]; values: (number | null)[][]; rowLabel: string; colLabel: string; reference?: number | null;
    fmt?: (v: number) => string; rowFmt?: (v: number) => string; colFmt?: (v: number) => string }) {
  const flat = values.flat().filter(isNum);
  const ref = reference ?? (flat.length ? flat[Math.floor(flat.length / 2)] : 1);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1 text-xs" aria-label={`Sensitivity: ${rowLabel} by ${colLabel}`}>
        <thead><tr><th className="px-1 text-left font-normal text-fg-3">{rowLabel} ↓ / {colLabel} →</th>
          {cols.map((c) => <th key={c} scope="col" className="num px-1 font-normal text-fg-3">{colFmt(c)}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r}>
              <th scope="row" className="num px-1 text-left font-normal text-fg-3">{rowFmt(r)}</th>
              {cols.map((c, j) => {
                const v = values[i]?.[j];
                if (!isNum(v)) return <td key={c} className="rounded bg-ink-800 px-2 py-2 text-center text-fg-3">n/a</td>;
                const t = Math.max(-1, Math.min(1, (v / ref - 1) / 0.5));
                const pole = t >= 0 ? "var(--color-s1)" : "#e66767";
                const strong = Math.abs(t) > 0.6;
                return (
                  <td key={c} title={`${rowLabel} ${rowFmt(r)}, ${colLabel} ${colFmt(c)}: ${fmt(v)}${reference ? ` (${((v / reference - 1) * 100).toFixed(0)}% vs price)` : ""}`}
                    className="num rounded px-2 py-2 text-center"
                    style={{ background: `color-mix(in oklab, ${pole} ${Math.abs(t) * 100}%, #383835)`, color: strong ? "#fff" : "var(--color-fg)" }}>
                    {fmt(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {reference && <p className="mt-1 text-[11px] text-fg-3">Blue: above today&apos;s price · grey ≈ price · red: below (saturates at ±50%).</p>}
    </div>
  );
}

export function Tornado({ bars, base, fmt = (v) => price(v) }: { bars: { assumption: string; low_input: string; high_input: string; low_value: number; high_value: number }[]; base: number; fmt?: (v: number) => string }) {
  const all = bars.flatMap((b) => [b.low_value, b.high_value]).concat(base);
  const lo = Math.min(...all), hi = Math.max(...all);
  const x = (v: number) => ((v - lo) / (hi - lo || 1)) * 100;
  return (
    <div className="space-y-2" role="list" aria-label="Valuation sensitivity by assumption">
      {bars.map((b) => (
        <div key={b.assumption} role="listitem" className="grid grid-cols-[minmax(120px,32%)_1fr] items-center gap-3 text-xs">
          <div className="truncate text-fg-2" title={b.assumption}>{b.assumption}</div>
          <div className="relative h-6 rounded bg-ink-850">
            <div className="absolute inset-y-0 w-px bg-fg-3" style={{ left: `${x(base)}%` }} aria-hidden />
            {[{ v: b.low_value, lbl: b.low_input, c: SERIES[1] }, { v: b.high_value, lbl: b.high_input, c: SERIES[0] }].map((p) => {
              const a = Math.min(x(base), x(p.v)), w = Math.abs(x(p.v) - x(base));
              return <div key={p.lbl} className="absolute inset-y-1 rounded-sm" style={{ left: `${a}%`, width: `${Math.max(w, 0.5)}%`, background: p.c }}
                title={`${b.assumption} ${p.lbl}: ${fmt(p.v)}`} />;
            })}
          </div>
        </div>
      ))}
      <Legend items={[{ label: "Unfavourable change", color: SERIES[1] }, { label: "Favourable change", color: SERIES[0] }]} />
    </div>
  );
}

export function RangeStrip({ bear, base, bull, current }: { bear: number; base: number; bull: number; current?: number | null }) {
  const vals = [bear, base, bull, ...(isNum(current) ? [current] : [])];
  const lo = Math.min(...vals) * 0.85, hi = Math.max(...vals) * 1.1;
  const x = (v: number) => ((v - lo) / (hi - lo)) * 100;
  return (
    <div className="relative h-20" role="img" aria-label={`Value range bear ${price(bear)}, base ${price(base)}, bull ${price(bull)}${isNum(current) ? `, price ${price(current)}` : ""}`}>
      <div className="absolute top-9 h-3 rounded-full bg-ink-700" style={{ left: `${x(bear)}%`, width: `${x(bull) - x(bear)}%` }} />
      {[["Bear", bear], ["Base", base], ["Bull", bull]].map(([l, v]) => (
        <div key={l as string} className="absolute top-0 -translate-x-1/2 text-center" style={{ left: `${x(v as number)}%` }}>
          <div className="num whitespace-nowrap text-[11px] text-fg-2">{l} {price(v)}</div>
          <div className="mx-auto mt-4 size-3 rounded-full border-2 border-ink-900 bg-s1" />
        </div>
      ))}
      {isNum(current) && (
        <div className="absolute top-5 -translate-x-1/2" style={{ left: `${x(current)}%` }}>
          <div className="mx-auto h-10 w-0.5 bg-fg" />
          <div className="num mt-0.5 whitespace-nowrap text-[11px] font-semibold text-fg">Price {price(current)}</div>
        </div>
      )}
    </div>
  );
}
