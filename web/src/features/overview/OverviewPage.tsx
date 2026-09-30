import { Link, useParams } from "react-router-dom";

import { Panel, StatusDot } from "../../components/ui";
import { formatKwh, formatPower, relativeTime } from "../../lib/format";
import { useSites } from "../../lib/queries";
import { useLive } from "../../lib/useLive";
import { summarize } from "./summary";
import "./overview.css";

export function OverviewPage() {
  const { siteId = "" } = useParams();
  const { data: sites } = useSites();
  const site = sites?.find((s) => s.id === siteId);
  const { snapshot, connected } = useLive(siteId);

  if (!snapshot) {
    return <p className="eyebrow">Connecting to live feed…</p>;
  }
  if (!snapshot.devices.length) {
    return (
      <Panel title="No devices yet" eyebrow={site?.name}>
        <p>Add an energy monitor to start collecting data.</p>
        <Link to={`/s/${siteId}/devices`}>Go to Devices</Link>
      </Panel>
    );
  }

  const summary = summarize(snapshot, site);
  const house = formatPower(summary.houseW);
  const peak = Math.max(1, ...summary.bars.map((b) => Math.abs(b.watts)));

  return (
    <div className="overview">
      <section className="readout" aria-labelledby="readout-label">
        <p className="eyebrow" id="readout-label">
          Whole house · live
        </p>
        <p className="readout-value num" aria-live="polite">
          {house.value}
          <span className="readout-unit">{house.unit}</span>
        </p>
        <dl className="readout-meta">
          <div>
            <dt>Today</dt>
            <dd className="num">{formatKwh(summary.todayKwh)} kWh</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{summary.source}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{relativeTime(snapshot.ts)}</dd>
          </div>
        </dl>
        {!connected && <p className="stale">Live feed reconnecting. Values may be stale.</p>}
        {summary.houseW === null && (
          <p className="stale">
            Mark your mains channels as <strong>grid main</strong> on the Devices page to see
            whole-house power.
          </p>
        )}
      </section>

      <Panel
        title="Devices"
        eyebrow={`${snapshot.devices.length} on this site`}
        className="devices-strip"
      >
        <ul className="device-list">
          {snapshot.devices.map((d) => (
            <li key={d.id}>
              <Link to={`/s/${siteId}/devices/${d.id}`}>{d.name}</Link>
              <StatusDot online={d.online} />
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Where the power goes" eyebrow="Circuits, ranked" className="loads">
        <table className="loads-table">
          <caption className="visually-hidden">Live power by circuit</caption>
          <thead className="visually-hidden">
            <tr>
              <th scope="col">Circuit</th>
              <th scope="col">Power</th>
            </tr>
          </thead>
          <tbody>
            {summary.bars.map((bar) => {
              const p = formatPower(bar.watts);
              const width = `${Math.max(0.5, (Math.abs(bar.watts) / peak) * 100)}%`;
              return (
                <tr
                  key={bar.id}
                  className={`load load-${bar.kind} ${bar.watts < 0 ? "load-negative" : ""}`}
                >
                  <th scope="row">
                    <span className="load-name">{bar.name}</span>
                    <span className="load-track" aria-hidden="true">
                      <span className="load-fill" style={{ width }} />
                    </span>
                  </th>
                  <td className="num">
                    {p.value} <span className="unit">{p.unit}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
