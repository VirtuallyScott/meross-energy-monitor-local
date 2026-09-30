import { formatKwh, formatPower, formatVoltage } from "../../lib/format";
import type { LiveChannel } from "../../lib/types";
import { mainsTotal } from "./readings";

/**
 * The main breaker end of the panel (PNL-010): one card per mains CT (A1, B1) with
 * voltage, power and today's energy, and their combined total. `null` means no live data yet.
 */
export function MainsStrip({ mains }: { mains: LiveChannel[] | null }) {
  if (mains === null) {
    return (
      <section className="panel-mains is-empty" aria-label="Mains">
        <p>Waiting for live data…</p>
      </section>
    );
  }
  if (!mains.length) {
    return (
      <section className="panel-mains is-empty" aria-label="Mains">
        <p>
          No mains channel. Set a channel's role to <strong>Grid main</strong> on its device page to
          show A1 and B1 here.
        </p>
      </section>
    );
  }
  const total = mainsTotal(mains);
  const power = formatPower(total.powerW);
  return (
    <section className="panel-mains" aria-label="Mains">
      <ul className="mains-legs">
        {mains.map((m) => (
          <MainsLeg key={m.id} channel={m} />
        ))}
      </ul>
      <p className="mains-total">
        <span className="eyebrow">Mains</span>
        <span className="num">
          {power.value}
          <span className="unit">{power.unit}</span>
        </span>
        <span className="num mains-kwh">
          {formatKwh(total.dayKwh)}
          <span className="unit">kWh today</span>
        </span>
      </p>
    </section>
  );
}

function MainsLeg({ channel }: { channel: LiveChannel }) {
  const volts = formatVoltage(channel.voltage_v);
  const power = formatPower(channel.power_w);
  return (
    <li className="mains-leg">
      <span className="mains-label">{channel.phase_label ?? "—"}</span>
      <span className="mains-name">{channel.name}</span>
      <dl className="mains-values">
        <div>
          <dt>Voltage</dt>
          <dd className="num">
            {volts.value}
            <span className="unit">{volts.unit}</span>
          </dd>
        </div>
        <div>
          <dt>Power</dt>
          <dd className={`num${channel.power_w ? " is-live" : ""}`}>
            {power.value}
            <span className="unit">{power.unit}</span>
          </dd>
        </div>
        <div>
          <dt>Today</dt>
          <dd className="num">
            {formatKwh(channel.day_kwh)}
            <span className="unit">kWh</span>
          </dd>
        </div>
      </dl>
    </li>
  );
}
