export class APIError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options, credentials: "same-origin", cache: "no-store",
    headers: {...(options.body && typeof options.body === "string" ? {"Content-Type": "application/json"} : {}), ...options.headers},
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data.error?.message ?? data.errors?.map((e: {path: (string | number)[]; message: string}) => `${e.path.join(".")}: ${e.message}`).join("; ") ?? "The request could not be completed.";
    throw new APIError(message, response.status);
  }
  return data as T;
}

export const post = <T>(path: string, value: unknown) => api<T>(path, {method: "POST", body: JSON.stringify(value)});

export type User = {id: string; email: string};
export type Project = {id: string; name: string; created_at: string; updated_at: string};
export type Circuit = {schema_version: string; name: string; components: {id: string; type: string; pins: string[]; value_ohms?: number}[]; nets: {id: string; members: string[]; role: string}[]; supply?: {voltage_v: number; current_limit_ma: number; positive_net: string; negative_net: string}};
export type Point = {x: number; y: number};
export type Board = {model_id: string; revision: string; verification_status: string; holes: {id: string; position: Point; conductive_group_id: string}[]; rail_segments: {id: string; label: string; hole_ids: string[]}[]};
export type Placement = {component_id: string; footprint_id: string; pins: Record<string, string>; anchor: string; orientation: number};
export type Step = {sequence: number; kind: string; title: string; instruction: string; holes: string[]; component_id: string | null};
export type Plan = {id: string; circuit_version_id: string; plan: {reference_only: boolean; layout: {board_model_id: string; board_revision: string; components: Placement[]; jumpers: {id: string; net_id: string; start: string; end: string; color: string}[]; supply: {positive_hole: string; negative_hole: string} | null}; steps: Step[]; validation: {valid: boolean; ready_to_build: boolean; warnings: {code: string; message: string}[]; errors: {code: string; message: string}[]}}};
export type Photo = {id: string; project_id: string; width: number; height: number; consent_for_training: boolean; expires_at: string};
export type ProjectDetail = Project & {circuits: {id: string; circuit: Circuit; digest: string}[]; plans: {id: string; circuit_version_id: string}[]; images: Photo[]};
export type Verification = {id: string; status: string; results: null | {status?: string; error?: string; holes: Record<string, Point>; overlay: {components: {component_id: string; pins: Record<string, Point>}[]; jumpers: {id: string; start: Point; end: Point; color: string}[]}; uncertainties: string[]; component_detection_available: boolean; electrically_verified: false}};
