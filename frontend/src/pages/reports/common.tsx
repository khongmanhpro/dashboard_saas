import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import type { Metric, RangeKey, RangeParams } from "../../api/reports";
import type { Me } from "../../api/types";
import { canSee, NAV } from "../../app/nav";
import { Icon } from "../../components/Icon";
import { format, t } from "../../i18n";
import { formatNumber, metricDelta, type DeltaKind } from "../../reports/format";

export function RangePicker({
  keys,
  value,
  onChange,
}: {
  keys: RangeKey[];
  value: RangeParams;
  onChange: (r: RangeParams) => void;
}) {
  return (
    <div className="range-picker">
      <div className="segmented" role="group" aria-label={t.reports.rangeLabel}>
        {keys.map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={value.range === key}
            onClick={() => onChange({ ...value, range: key })}
          >
            {t.reports.ranges[key]}
          </button>
        ))}
      </div>
      {value.range === "custom" ? (
        <span className="range-picker__dates" title={t.reports.rangeHint}>
          <label>
            <span className="sr-only">{t.reports.from}</span>
            <input
              type="date"
              value={value.from ?? ""}
              aria-label={t.reports.from}
              onChange={(e) => onChange({ ...value, from: e.target.value })}
            />
          </label>
          <span aria-hidden="true">–</span>
          <label>
            <span className="sr-only">{t.reports.to}</span>
            <input
              type="date"
              value={value.to ?? ""}
              aria-label={t.reports.to}
              onChange={(e) => onChange({ ...value, to: e.target.value })}
            />
          </label>
        </span>
      ) : null}
    </div>
  );
}

export function KpiCard({
  label,
  value,
  metric,
  kind,
  better,
  note,
  hint,
}: {
  label: string;
  value: string;
  metric?: Metric | null;
  kind?: DeltaKind;
  better?: "up" | "down";
  note?: string;
  hint?: string;
}) {
  const delta = metric && kind && better ? metricDelta(metric, kind, better) : null;
  return (
    <div className="kpi" title={hint}>
      <div className="kpi__label">{label}</div>
      <div className="kpi__value">{value}</div>
      {delta ? (
        <div className={`kpi__delta kpi__delta--${delta.tone}`}>
          {delta.text}{" "}
          <span className="muted">
            {delta.isNew && metric?.previous != null
              ? format(t.reports.previousValue, { v: formatNumber(metric.previous) })
              : t.reports.vsPrevious}
          </span>
        </div>
      ) : note ? (
        <div className="kpi__delta muted">{note}</div>
      ) : null}
    </div>
  );
}

export function StatusPill({ tone, children }: { tone: "good" | "bad" | "warn" | "neutral"; children: ReactNode }) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}

export function MissingFx({ currencies }: { currencies: string[] }) {
  if (currencies.length === 0) return null;
  return (
    <div className="notice notice--warn" role="status">
      {format(t.reports.missingFx, { currencies: currencies.join(", ") })}
    </div>
  );
}

const MOBILE_KEYS = ["overview", "staff", "leads", "ads"] as const;

/** Thanh menu dưới khi màn hình hẹp (Mobile.dc.html). Máy tính dùng menu trái. */
export function MobileNav({ me }: { me: Me }) {
  const items = MOBILE_KEYS.map((key) => NAV.find((i) => i.key === key)).filter(
    (item): item is (typeof NAV)[number] => item !== undefined && canSee(item, me.permissions),
  );
  if (items.length < 2) return null;
  return (
    <nav className="mobile-nav" aria-label={t.overview.mobileLabel}>
      {items.map((item) => (
        <NavLink key={item.key} to={item.path}>
          <Icon name={item.icon} />
          {t.overview.mobileNav[item.key as (typeof MOBILE_KEYS)[number]]}
        </NavLink>
      ))}
    </nav>
  );
}
