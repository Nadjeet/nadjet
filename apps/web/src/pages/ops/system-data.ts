import type { components } from "@nadjet/api-client";

import { api } from "@/api";

export type CameraSystemStatus = components["schemas"]["CameraSystemStatus"];

export async function fetchSystemCameras(): Promise<CameraSystemStatus[]> {
  const { data, error } = await api.GET("/system/cameras");
  if (!data) throw new Error(`system cameras: ${JSON.stringify(error)}`);
  return data;
}
