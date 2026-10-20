"use client";

import { useMemo, useState } from "react";
import type { Board, Plan, Point } from "@/lib/api";

const colors: Record<string, string> = {
  red: "#cc4a3f",
  black: "#33443c",
  blue: "#477cd0",
  green: "#25866a",
  yellow: "#c89624",
};

export default function BreadboardViewer({
  board,
  plan,
  highlighted = [],
}: {
  board: Board;
  plan: Plan;
  highlighted?: string[];
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const holes = useMemo(
    () => new Map(board.holes.map((h) => [h.id, h])),
    [board],
  );
  const coordinates = board.holes.map((h) => h.position);
  const minX = Math.min(...coordinates.map((p) => p.x)) - 8;
  const maxX = Math.max(...coordinates.map((p) => p.x)) + 8;
  const minY = Math.min(...coordinates.map((p) => p.y)) - 8;
  const maxY = Math.max(...coordinates.map((p) => p.y)) + 8;
  const position = (id: string): Point => {
    const p = holes.get(id)!.position;
    return { x: p.y, y: p.x };
  };
  const selectedGroup = selected
    ? holes.get(selected)?.conductive_group_id
    : undefined;
  const active = new Set(highlighted);
  const layout = plan.plan.layout;
  const pointList = (pins: Record<string, string>) =>
    Object.values(pins).map(position);

  return (
    <div className="board-viewer">
      <div className="board-toolbar">
        <span className="eyebrow">830 CONTACTS · REFERENCE r1</span>
        <span className="legend">
          <i className="dot green" />
          Active step <i className="dot blue" />
          Jumper
        </span>
      </div>
      <div className="board-scroll">
        <svg
          className="breadboard"
          viewBox={`${minY} ${minX} ${maxY - minY} ${maxX - minX}`}
          role="group"
          aria-label="Interactive reference breadboard with planned components and jumper endpoints"
        >
          <rect
            x={minY + 1}
            y={minX + 1}
            width={maxY - minY - 2}
            height={maxX - minX - 2}
            rx="3"
            fill="#eeeade"
            stroke="#d1cebf"
            strokeWidth="0.4"
          />
          {board.rail_segments.map((segment) => {
            const first = position(segment.hole_ids[0]),
              last = position(segment.hole_ids.at(-1)!);
            return (
              <g key={segment.id}>
                <line
                  x1={first.x}
                  x2={last.x}
                  y1={first.y - 1.5}
                  y2={last.y - 1.5}
                  stroke={segment.label === "+" ? "#c7776c" : "#7a9eb5"}
                  strokeWidth="0.3"
                />
                <text
                  x={first.x - 4}
                  y={first.y + 0.7}
                  fontSize="2.3"
                  fill="#7a776b"
                >
                  {segment.label}
                </text>
              </g>
            );
          })}
          {board.holes
            .filter(
              (h) =>
                h.id.startsWith("A") &&
                [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 63].includes(
                  Number(h.id.slice(1)),
                ),
            )
            .map((h) => (
              <text
                key={`number-${h.id}`}
                x={position(h.id).x}
                y={position(h.id).y - 3.1}
                textAnchor="middle"
                fontSize="1.7"
                fill="#8b8778"
              >
                {h.id.slice(1)}
              </text>
            ))}
          {board.holes
            .filter((h) => /^[A-J]1$/.test(h.id))
            .map((h) => (
              <text
                key={`column-${h.id}`}
                x={position(h.id).x - 4}
                y={position(h.id).y + 0.6}
                fontSize="1.8"
                fill="#8b8778"
              >
                {h.id[0]}
              </text>
            ))}
          {board.holes.map((h) => {
            const p = position(h.id),
              selectedStrip = h.conductive_group_id === selectedGroup;
            const lit = active.has(h.id);
            return (
              <circle
                key={h.id}
                cx={p.x}
                cy={p.y}
                r={lit ? 0.95 : 0.65}
                fill={lit ? "#159b73" : selectedStrip ? "#dea749" : "#77796e"}
                stroke={
                  h.id === selected ? "#064d3a" : lit ? "#abecd6" : "#d9d5c7"
                }
                strokeWidth={lit || h.id === selected ? 0.5 : 0.2}
                role="button"
                tabIndex={0}
                aria-label={`Hole ${h.id}`}
                onClick={() => setSelected(h.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelected(h.id);
                  }
                }}
              >
                <title>
                  {h.id} · {h.conductive_group_id}
                </title>
              </circle>
            );
          })}
          {layout.jumpers.map((wire) => {
            const a = position(wire.start),
              b = position(wire.end),
              lift = Math.min(9, Math.abs(a.x - b.x) / 5 + 3);
            return (
              <path
                key={wire.id}
                d={`M${a.x} ${a.y} Q${(a.x + b.x) / 2} ${Math.min(a.y, b.y) - lift} ${b.x} ${b.y}`}
                fill="none"
                stroke={colors[wire.color]}
                strokeWidth=".65"
                strokeLinecap="round"
                opacity={
                  !active.size ||
                  (active.has(wire.start) && active.has(wire.end))
                    ? 1
                    : 0.24
                }
              >
                <title>
                  {wire.id}: {wire.start} → {wire.end} ({wire.net_id})
                </title>
              </path>
            );
          })}
          {layout.components.map((component) => {
            const points = pointList(component.pins),
              a = points[0],
              b = points.at(-1)!;
            const cx = (a.x + b.x) / 2,
              cy = (a.y + b.y) / 2;
            const angle = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
            const lit =
              !active.size ||
              Object.values(component.pins).some((id) => active.has(id));
            return (
              <g
                key={component.component_id}
                opacity={lit ? 1 : 0.3}
                pointerEvents="none"
              >
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke="#6e766d"
                  strokeWidth=".55"
                />
                {component.footprint_id.startsWith("resistor") ? (
                  <g transform={`translate(${cx} ${cy}) rotate(${angle})`}>
                    <rect
                      x="-2.3"
                      y="-.95"
                      width="4.6"
                      height="1.9"
                      rx=".6"
                      fill="#d4b486"
                      stroke="#91744c"
                      strokeWidth=".3"
                    />
                    <path
                      d="M-1 -1 v2 M0 -1 v2 M1 -1 v2"
                      stroke="#765e49"
                      strokeWidth=".45"
                    />
                  </g>
                ) : component.footprint_id.startsWith("led") ? (
                  <circle
                    cx={cx}
                    cy={cy}
                    r="1.25"
                    fill="#e36f55"
                    fillOpacity=".9"
                    stroke="#a84b36"
                    strokeWidth=".3"
                  />
                ) : component.footprint_id.startsWith("button") ? (
                  <g>
                    <rect
                      x={Math.min(...points.map((p) => p.x)) - 1}
                      y={Math.min(...points.map((p) => p.y)) - 1}
                      width={Math.abs(a.x - b.x) + 2}
                      height={Math.abs(a.y - b.y) + 2}
                      rx=".5"
                      fill="#35483e"
                    />
                    <circle cx={cx} cy={cy} r="1.5" fill="#9ea89d" />
                  </g>
                ) : (
                  <circle cx={cx} cy={cy} r="1" fill="#8cab83" />
                )}
                <text
                  x={cx}
                  y={cy - 2.2}
                  textAnchor="middle"
                  fontSize="2.1"
                  fontWeight="700"
                  fill="#214c3a"
                  stroke="#eeeade"
                  strokeWidth=".3"
                  paintOrder="stroke"
                >
                  {component.component_id}
                </text>
              </g>
            );
          })}
          {layout.supply &&
            (
              [
                ["positive_hole", "+", "#bd5747"],
                ["negative_hole", "−", "#32443c"],
              ] as const
            ).map(([key, label, color]) => {
              const p = position(layout.supply![key]);
              return (
                <g key={key} pointerEvents="none">
                  <circle cx={p.x} cy={p.y} r="1.4" fill={color} />
                  <text
                    x={p.x}
                    y={p.y + 0.7}
                    fill="white"
                    textAnchor="middle"
                    fontSize="2"
                  >
                    {label}
                  </text>
                </g>
              );
            })}
        </svg>
      </div>
      <div className="board-caption">
        <span>
          {selected ? (
            <>
              <strong>{selected}</strong> · {selectedGroup} ·{" "}
              {
                board.holes.filter(
                  (h) => h.conductive_group_id === selectedGroup,
                ).length
              }{" "}
              directly connected holes
            </>
          ) : (
            "Select a hole to inspect its conductive strip."
          )}
        </span>
        <span>Coordinates from board model</span>
      </div>
    </div>
  );
}
