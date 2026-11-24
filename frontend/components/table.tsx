"use client";

import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from "@tanstack/react-table";
import clsx from "clsx";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useState } from "react";

export function DataTable<T>({ data, columns, empty = "No rows", dense, caption }:
  { data: T[]; columns: ColumnDef<T, unknown>[]; empty?: string; dense?: boolean; caption?: string }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({ data, columns, state: { sorting }, onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  return (
    <div className="scroll-thin overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-ink-700">
              {hg.headers.map((h) => {
                const s = h.column.getIsSorted();
                const right = (h.column.columnDef.meta as { right?: boolean } | undefined)?.right;
                return (
                  <th key={h.id} scope="col" aria-sort={s === "asc" ? "ascending" : s === "desc" ? "descending" : "none"}
                    className={clsx("whitespace-nowrap px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-fg-3", right ? "text-right" : "text-left")}>
                    {h.column.getCanSort() ? (
                      <button onClick={h.column.getToggleSortingHandler()} className={clsx("inline-flex items-center gap-1 hover:text-fg", right && "flex-row-reverse")}>
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {s === "asc" ? <ArrowUp size={11} /> : s === "desc" ? <ArrowDown size={11} /> : <ArrowUpDown size={11} className="opacity-40" />}
                      </button>
                    ) : flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length === 0 && <tr><td colSpan={columns.length} className="px-3 py-6 text-center text-fg-3">{empty}</td></tr>}
          {table.getRowModel().rows.map((r) => (
            <tr key={r.id} className="border-b border-ink-800 hover:bg-ink-850">
              {r.getVisibleCells().map((c) => (
                <td key={c.id} className={clsx("px-3 align-top", dense ? "py-1.5" : "py-2",
                  (c.column.columnDef.meta as { right?: boolean } | undefined)?.right && "num text-right")}>
                  {flexRender(c.column.columnDef.cell, c.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
