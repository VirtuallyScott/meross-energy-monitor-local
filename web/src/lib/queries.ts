import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import type { Circuit, Device, Me, Panel, Site } from "./types";

export const useMe = () =>
  useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/auth/me"), retry: false });
export const useSites = () =>
  useQuery({ queryKey: ["sites"], queryFn: () => api<Site[]>("/sites") });
export const useDevices = (siteId: string) =>
  useQuery({
    queryKey: ["devices", siteId],
    queryFn: () => api<Device[]>(`/devices?site_id=${siteId}`),
    refetchInterval: 30_000,
  });
export const useDevice = (id: string) =>
  useQuery({ queryKey: ["device", id], queryFn: () => api<Device>(`/devices/${id}`) });
export const useCircuits = (siteId: string) =>
  useQuery({
    queryKey: ["circuits", siteId],
    queryFn: () => api<Circuit[]>(`/circuits?site_id=${siteId}`),
  });
export const usePanels = (siteId: string) =>
  useQuery({
    queryKey: ["panels", siteId],
    queryFn: () => api<Panel[]>(`/panels?site_id=${siteId}`),
  });
