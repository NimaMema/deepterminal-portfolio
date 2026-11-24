"use client";

import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

export interface GraphEdge { entity: string; type: string; relation: string; country: string | null; verification_status: string; evidence_id: number | null; excerpt: string | null }

const COLOR: Record<string, string> = { manufacturer: "#3987e5", supplier: "#199e70", counterparty: "#8593a6" };

export function SupplyGraph({ center, edges, onSelect }: { center: string; edges: GraphEdge[]; onSelect: (e: GraphEdge) => void }) {
  const { nodes, links } = useMemo(() => {
    const countries = Array.from(new Set(edges.map((e) => e.country).filter(Boolean))) as string[];
    const n: Node[] = [{ id: "c", position: { x: 0, y: 0 }, data: { label: center },
      style: { background: "#0f2e2b", color: "#e7edf4", border: "1.5px solid #2dd4bf", borderRadius: 10, fontWeight: 600, fontSize: 12, width: 190 } }];
    const l: Edge[] = [];
    const R = 260;
    edges.forEach((e, i) => {
      const a = (2 * Math.PI * i) / Math.max(edges.length, 1) - Math.PI / 2;
      const id = `e${i}`;
      n.push({ id, position: { x: Math.cos(a) * R, y: Math.sin(a) * R }, data: { label: e.entity, edge: e },
        style: { background: "#131a24", color: "#e7edf4", border: `1.5px solid ${COLOR[e.type] ?? "#8593a6"}`, borderRadius: 8, fontSize: 11, width: 170, cursor: "pointer" } });
      l.push({ id: `l${i}`, source: id, target: "c", label: e.relation, animated: e.relation.startsWith("sole"),
        style: { stroke: e.relation.startsWith("sole") ? "#f05252" : COLOR[e.type] ?? "#8593a6", strokeWidth: 1.5 },
        labelStyle: { fill: "#b6c2d1", fontSize: 10 }, labelBgStyle: { fill: "#0b0f15" } });
    });
    countries.forEach((c, i) => {
      const a = (2 * Math.PI * i) / Math.max(countries.length, 1);
      const id = `k${i}`;
      n.push({ id, position: { x: Math.cos(a) * (R + 210), y: Math.sin(a) * (R + 160) }, data: { label: `📍 ${c}` },
        style: { background: "transparent", color: "#b6c2d1", border: "1px dashed #3a4a60", borderRadius: 999, fontSize: 11, width: 130 } });
      edges.forEach((e, j) => { if (e.country === c) l.push({ id: `kc${i}-${j}`, source: `e${j}`, target: id, style: { stroke: "#3a4a60", strokeDasharray: "3 3" } }); });
    });
    return { nodes: n, links: l };
  }, [center, edges]);
  return (
    <div className="h-[520px] rounded-lg border border-ink-700 bg-ink-950" role="application" aria-label="Supplier relationship graph. Select a node to see its evidence.">
      <ReactFlow nodes={nodes} edges={links} fitView proOptions={{ hideAttribution: true }} nodesConnectable={false}
        onNodeClick={(_, node) => { const e = (node.data as { edge?: GraphEdge }).edge; if (e) onSelect(e); }} colorMode="dark">
        <Background color="#1b2431" gap={24} /><Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
