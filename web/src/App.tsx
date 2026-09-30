import { useQuery } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import { Alert } from "./components/ui";
import { LoginPage, SetupPage } from "./features/auth/AuthPages";
import { DeviceDetailPage } from "./features/devices/DeviceDetailPage";
import { DevicesPage } from "./features/devices/DevicesPage";
import { HistoryPage } from "./features/history/HistoryPage";
import { Shell } from "./features/layout/Shell";
import { OverviewPage } from "./features/overview/OverviewPage";
import { PanelsPage } from "./features/panels/PanelsPage";
import { api, ApiError, errorMessage } from "./lib/api";
import { useMe, useSites } from "./lib/queries";

function FirstSite() {
  const { data: sites, isLoading } = useSites();
  if (isLoading) return null;
  const first = sites?.[0];
  if (!first)
    return <Alert tone="info">You do not have access to any site yet. Ask an administrator.</Alert>;
  return <Navigate to={`/s/${first.id}/overview`} replace />;
}

export function App() {
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => api<{ needs_setup: boolean }>("/setup/status"),
  });
  const me = useMe();

  if (setup.isLoading || me.isLoading) return null;
  if (setup.data?.needs_setup) return <SetupPage />;
  if (me.error instanceof ApiError && me.error.status === 401) return <LoginPage />;
  if (me.error || setup.error) {
    return (
      <main className="content">
        <Alert>{errorMessage(me.error ?? setup.error)}</Alert>
      </main>
    );
  }

  return (
    <Routes>
      <Route path="/s/:siteId" element={<Shell />}>
        <Route path="overview" element={<OverviewPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="panels" element={<PanelsPage />} />
        <Route path="devices" element={<DevicesPage />} />
        <Route path="devices/:deviceId" element={<DeviceDetailPage />} />
        <Route index element={<Navigate to="overview" replace />} />
      </Route>
      <Route path="*" element={<FirstSite />} />
    </Routes>
  );
}
