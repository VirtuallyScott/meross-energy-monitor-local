import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { Alert, Button, Field, Panel, Select } from "../../components/ui";
import { api, errorMessage, patch, post } from "../../lib/api";
import { formatPower } from "../../lib/format";
import { useMe, usePanels } from "../../lib/queries";
import {
  hasPerm,
  type LiveChannel,
  type Panel as PanelModel,
  type PanelNumbering,
} from "../../lib/types";
import { useLive } from "../../lib/useLive";
import { BreakerCell } from "./BreakerCell";
import { layoutPanel } from "./layout";
import { MainsStrip } from "./MainsStrip";
import { panelMains, parseMetric, type Reading, readingsById, type SlotMetric } from "./readings";
import "./panels.css";

const NUMBERINGS: { value: PanelNumbering; label: string }[] = [
  { value: "odd_even", label: "Odd left, even right" },
  { value: "sequential", label: "Left column, then right" },
];

const METRICS: { value: SlotMetric; label: string }[] = [
  { value: "watts", label: "Power (W)" },
  { value: "amps", label: "Current (A)" },
];

/** Spatial view of each electrical panel with mains and live readings per space (PNL-006, PNL-010, PNL-011). */
export function PanelsPage() {
  const { siteId = "" } = useParams();
  const { data: me } = useMe();
  const { data: panels, error, isLoading } = usePanels(siteId);
  const { snapshot } = useLive(siteId);
  const canManage = hasPerm(me, "device:manage", siteId);
  const [adding, setAdding] = useState(false);
  const [params, setParams] = useSearchParams();
  const metric = parseMetric(params.get("show"));
  const setMetric = (value: SlotMetric) => {
    const next = new URLSearchParams(params);
    if (value === "watts") next.delete("show");
    else next.set("show", value);
    setParams(next, { replace: true });
  };

  const live = useMemo(() => readingsById(snapshot?.channels ?? []), [snapshot]);

  if (error) return <Alert>{errorMessage(error)}</Alert>;
  if (isLoading || !panels) return <p className="eyebrow">Loading…</p>;

  return (
    <div className="panels-page">
      <header className="panels-intro">
        <div>
          <p className="eyebrow">Load centers</p>
          <h1>Panels</h1>
          <p className="lede">
            Breakers sit where they are in the real panel. Place a channel on its breaker from the{" "}
            <Link to={`/s/${siteId}/devices`}>device page</Link>.
          </p>
        </div>
        <div className="panels-controls">
          <fieldset className="segmented">
            <legend>Each space shows voltage and</legend>
            {METRICS.map((m) => (
              <button
                key={m.value}
                type="button"
                aria-pressed={m.value === metric}
                onClick={() => setMetric(m.value)}
              >
                {m.label}
              </button>
            ))}
          </fieldset>
          {canManage && !adding && (
            <Button tone="primary" onClick={() => setAdding(true)}>
              Add panel
            </Button>
          )}
        </div>
      </header>

      {adding && (
        <Panel title="New panel">
          <PanelForm siteId={siteId} onDone={() => setAdding(false)} />
        </Panel>
      )}

      {panels.length === 0 && !adding && (
        <Alert tone="info">
          No panels yet.{" "}
          {canManage ? "Add your main panel to start." : "Ask a site manager to add one."}
        </Alert>
      )}

      {panels.map((p) => (
        <PanelCard
          key={p.id}
          panel={p}
          live={live}
          liveChannels={snapshot?.channels ?? null}
          metric={metric}
          canManage={canManage}
        />
      ))}
    </div>
  );
}

interface PanelCardProps {
  panel: PanelModel;
  live: Record<string, Reading>;
  /** Snapshot channels, or null before the first live frame arrives. */
  liveChannels: LiveChannel[] | null;
  metric: SlotMetric;
  canManage: boolean;
}

function PanelCard({ panel, live, liveChannels, metric, canManage }: PanelCardProps) {
  const { siteId = "" } = useParams();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const remove = useMutation({
    mutationFn: () => api(`/panels/${panel.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["panels", siteId] }),
  });
  const { breakers, empty } = layoutPanel(panel, live);
  const mains = liveChannels && panelMains(panel, liveChannels);
  const known = breakers.filter((b) => b.reading.powerW !== null);
  const totalW = known.length ? known.reduce((sum, b) => sum + (b.reading.powerW ?? 0), 0) : null;
  const total = formatPower(totalW);
  const rows = panel.spaces / 2;

  const confirmDelete = () => {
    if (window.confirm(`Delete ${panel.name}? Channels on it lose their breaker position.`)) {
      remove.mutate();
    }
  };

  return (
    <Panel
      title={panel.name}
      eyebrow={`${panel.spaces} spaces · ${breakers.length} monitored breakers`}
      actions={
        canManage && (
          <>
            <Button onClick={() => setEditing((v) => !v)}>{editing ? "Close" : "Edit"}</Button>
            <Button tone="danger" onClick={confirmDelete} disabled={remove.isPending}>
              Delete
            </Button>
          </>
        )
      }
    >
      {remove.isError && <Alert>{errorMessage(remove.error)}</Alert>}
      {editing && <PanelForm siteId={siteId} panel={panel} onDone={() => setEditing(false)} />}
      <p className="panel-total">
        <span className="eyebrow">Monitored now</span>
        <span className="num">
          {total.value} <span className="unit">{total.unit}</span>
        </span>
      </p>
      <div className="panel-enclosure">
        <MainsStrip mains={mains} />
        <div className="panel-face" style={{ "--rows": rows } as CSSProperties}>
          <span className="bus" aria-hidden="true" />
          <SpaceNumbers panel={panel} />
          <ol className="breakers" aria-label={`${panel.name} breakers`}>
            {breakers.map((b) => (
              <BreakerCell key={b.key} breaker={b} siteId={siteId} metric={metric} />
            ))}
          </ol>
          {empty.map((e) => (
            <span
              key={e.slot}
              className="space-empty"
              aria-hidden="true"
              style={{ gridRow: e.row + 1, gridColumn: e.column === 0 ? 2 : 4 }}
            />
          ))}
        </div>
      </div>
    </Panel>
  );
}

function SpaceNumbers({ panel }: { panel: PanelModel }) {
  const rows = panel.spaces / 2;
  return Array.from({ length: rows }, (_, row) => {
    const [left, right] =
      panel.numbering === "odd_even" ? [row * 2 + 1, row * 2 + 2] : [row + 1, row + 1 + rows];
    return [
      <span key={`l${row}`} className="space-no" style={{ gridRow: row + 1, gridColumn: 1 }}>
        {left}
      </span>,
      <span key={`r${row}`} className="space-no" style={{ gridRow: row + 1, gridColumn: 5 }}>
        {right}
      </span>,
    ];
  });
}

function PanelForm({
  siteId,
  panel,
  onDone,
}: {
  siteId: string;
  panel?: PanelModel;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(panel?.name ?? "Main panel");
  const [spaces, setSpaces] = useState(panel?.spaces ?? 40);
  const [numbering, setNumbering] = useState<PanelNumbering>(panel?.numbering ?? "odd_even");
  const save = useMutation({
    mutationFn: () =>
      panel
        ? patch(`/panels/${panel.id}`, { name, spaces, numbering })
        : post("/panels", { site_id: siteId, name, spaces, numbering }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["panels", siteId] });
      onDone();
    },
  });
  return (
    <form
      className="panel-form"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
      <Field
        label="Name"
        value={name}
        maxLength={120}
        required
        onChange={(e) => setName(e.target.value)}
      />
      <Field
        label="Breaker spaces"
        type="number"
        min={2}
        max={84}
        step={2}
        required
        value={spaces}
        hint="Count every space, including blanks. Even number, 2 to 84."
        onChange={(e) => setSpaces(Number(e.target.value))}
      />
      <Select
        label="Space numbering"
        value={numbering}
        onChange={(e) => setNumbering(e.target.value as PanelNumbering)}
      >
        {NUMBERINGS.map((n) => (
          <option key={n.value} value={n.value}>
            {n.label}
          </option>
        ))}
      </Select>
      <div className="panel-form-actions">
        <Button tone="primary" type="submit" disabled={save.isPending}>
          {panel ? "Save panel" : "Add panel"}
        </Button>
        <Button type="button" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
