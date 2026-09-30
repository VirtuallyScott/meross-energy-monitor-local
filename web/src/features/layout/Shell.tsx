import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";

import { post } from "../../lib/api";
import { useMe, useSites } from "../../lib/queries";
import "./shell.css";

const NAV = [
  { to: "overview", label: "Overview" },
  { to: "history", label: "History" },
  { to: "panels", label: "Panels" },
  { to: "devices", label: "Devices" },
];

export function Shell() {
  const { siteId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const { data: sites = [] } = useSites();
  const logout = useMutation({
    mutationFn: () => post("/auth/logout"),
    onSettled: () => qc.clear(),
  });

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
            <rect width="32" height="32" rx="7" fill="currentColor" />
            <path d="M18 4 8 18h7l-2 10 11-15h-7z" fill="var(--amber)" />
          </svg>
          <span>Energy Hub</span>
        </div>
        <nav aria-label="Main navigation" className="mainnav">
          {NAV.map((item) => (
            <NavLink key={item.to} to={`/s/${siteId}/${item.to}`}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-end">
          {sites.length > 1 && (
            <label className="site-switch">
              <span className="visually-hidden">Site</span>
              <select value={siteId} onChange={(e) => navigate(`/s/${e.target.value}/overview`)}>
                {sites.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {sites.length === 1 && <span className="site-name">{sites[0]?.name}</span>}
          <button className="linkish" onClick={() => logout.mutate()}>
            Sign out {me ? <span className="num">({me.username})</span> : null}
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
