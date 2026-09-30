import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Alert, Button, Field, Select } from "../../components/ui";
import { api, errorMessage, put } from "../../lib/api";
import type { Channel, Panel } from "../../lib/types";
import { occupied } from "../panels/layout";

const POLES = [
  { value: 1, label: "Single-pole" },
  { value: 2, label: "Double-pole" },
  { value: 3, label: "Triple-pole" },
];

interface SensorOption {
  id: string;
  label: string;
}

type Legs = Record<number, string>;

const sensorLabel = (phase: string | null, name: string, fallback: number | string) => {
  const position = phase ?? String(fallback);
  return name === position ? position : `${position} · ${name}`;
};

/** Current sensors on the channel's breaker by pole, or just this channel on pole 1. */
function initialLegs(channel: Channel, panel: Panel | undefined): Legs {
  if (!panel || channel.panel_slot === null) return { 1: channel.id };
  return Object.fromEntries(
    panel.breakers.filter((b) => b.slot === channel.panel_slot).map((b) => [b.pole, b.channel_id]),
  );
}

/** Sensors on this device, plus any from other devices already on the breaker. */
function sensorOptions(deviceChannels: Channel[], panel: Panel | undefined): SensorOption[] {
  const own = deviceChannels.map((c) => ({
    id: c.id,
    label: sensorLabel(c.phase_label, c.name, c.channel_no),
  }));
  const ownIds = new Set(own.map((o) => o.id));
  const foreign = (panel?.breakers ?? [])
    .filter((b) => !ownIds.has(b.channel_id))
    .map((b) => ({
      id: b.channel_id,
      label: `${sensorLabel(b.phase_label, b.channel_name, "?")} (${b.device_name})`,
    }));
  return [...own, ...foreign];
}

/**
 * Panel, space, poles, rating and the sensor on each pole of a channel's breaker
 * (PNL-002, PNL-005). A double-pole breaker can carry one CT per leg, for example
 * A2 on space 1 and B2 on space 3, so an unbalanced 240 V load shows per leg.
 */
export function BreakerEditor({
  channel,
  deviceChannels,
  panels,
  siteId,
  deviceId,
  onDone,
}: {
  channel: Channel;
  deviceChannels: Channel[];
  panels: Panel[];
  siteId: string;
  deviceId: string;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const current = panels.find((p) => p.id === channel.panel_id);
  const [panelId, setPanelId] = useState(current?.id ?? panels[0]?.id ?? "");
  const [slot, setSlot] = useState(channel.panel_slot?.toString() ?? "");
  const [poles, setPoles] = useState(channel.breaker_poles ?? 1);
  const [amps, setAmps] = useState(channel.breaker_amps?.toString() ?? "");
  const [legs, setLegs] = useState<Legs>(() => initialLegs(channel, current));

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["device", deviceId] });
    qc.invalidateQueries({ queryKey: ["panels", siteId] });
    onDone();
  };
  const save = useMutation({
    mutationFn: () =>
      put(`/panels/${panelId}/breakers/${Number(slot)}`, {
        poles,
        amps: amps ? Number(amps) : null,
        legs: Object.entries(legs)
          .filter(([pole, id]) => id && Number(pole) <= poles)
          .map(([pole, id]) => ({ pole: Number(pole), channel_id: id })),
      }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () =>
      api(`/panels/${channel.panel_id}/breakers/${channel.panel_slot}`, { method: "DELETE" }),
    onSuccess: refresh,
  });

  if (panels.length === 0) {
    return (
      <p className="field-hint">
        No panels yet. <Link to={`/s/${siteId}/panels`}>Add a panel</Link> first, then place this
        channel on its breaker.
      </p>
    );
  }

  const panel = panels.find((p) => p.id === panelId);
  const start = Number(slot);
  const spaces = panel && start >= 1 ? occupied(start, poles, panel.numbering) : [];
  const chosen = Object.entries(legs)
    .filter(([pole, id]) => id && Number(pole) <= poles)
    .map(([, id]) => id);
  const duplicate = new Set(chosen).size !== chosen.length;
  const options = sensorOptions(deviceChannels, current);
  const busy = save.isPending || remove.isPending;

  return (
    <form
      className="breaker-form"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
      {remove.isError && <Alert>{errorMessage(remove.error)}</Alert>}
      <Select label="Panel" value={panelId} onChange={(e) => setPanelId(e.target.value)}>
        {panels.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </Select>
      <Field
        label="Space"
        type="number"
        min={1}
        max={panel?.spaces}
        required
        value={slot}
        hint={poles > 1 ? "The top space the breaker covers." : undefined}
        onChange={(e) => setSlot(e.target.value)}
      />
      <Select label="Poles" value={poles} onChange={(e) => setPoles(Number(e.target.value))}>
        {POLES.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </Select>
      <Field
        label="Rating (A)"
        type="number"
        min={1}
        max={400}
        value={amps}
        onChange={(e) => setAmps(e.target.value)}
      />

      <fieldset className="breaker-legs-field">
        <legend>{poles > 1 ? "Sensor on each pole" : "Sensor"}</legend>
        {Array.from({ length: poles }, (_, i) => i + 1).map((pole) => (
          <Select
            key={pole}
            label={spaces[pole - 1] ? `Space ${spaces[pole - 1]}` : `Pole ${pole}`}
            value={legs[pole] ?? ""}
            onChange={(e) => setLegs({ ...legs, [pole]: e.target.value })}
          >
            <option value="">No sensor</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </Select>
        ))}
        {duplicate && (
          <p className="field-hint field-error" role="alert">
            A sensor can read only one pole.
          </p>
        )}
      </fieldset>

      <div className="breaker-form-actions">
        <Button
          tone="primary"
          type="submit"
          disabled={busy || !slot || chosen.length === 0 || duplicate}
        >
          Save breaker
        </Button>
        {channel.panel_id && (
          <Button tone="danger" type="button" disabled={busy} onClick={() => remove.mutate()}>
            Remove breaker
          </Button>
        )}
      </div>
    </form>
  );
}
