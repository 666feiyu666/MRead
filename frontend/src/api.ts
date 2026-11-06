import type {
  Case,
  Decision,
  Material,
  MaterialDetail,
  PreviewStep,
  Profile,
  RunDetail,
  RunSummary,
  RuntimeConfig,
  Workflow,
  WorkflowDefinition,
} from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* keep the status line */
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

function json(body: unknown, method = 'POST'): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export const api = {
  runtimeConfig: () => request<RuntimeConfig>('/config'),

  listCases: () => request<Case[]>('/cases'),
  createCase: (title: string) => request<Case>('/cases', json({ title })),
  getCase: (id: string) =>
    request<Case & { assets: Material[]; workflows: Workflow[]; runs: RunSummary[] }>(`/cases/${id}`),

  listMaterials: (caseId: string) =>
    request<{ assets: Material[] }>(`/cases/${caseId}`).then((body) => body.assets),
  material: (id: string) => request<MaterialDetail>(`/assets/${id}`),
  uploadMaterial: (caseId: string, form: FormData) =>
    request<Material>(`/cases/${caseId}/assets`, { method: 'POST', body: form }),

  seedProfiles: () => request<Profile[]>('/profiles/seed', json({})),
  listProfiles: () => request<Profile[]>('/profiles'),
  createProfile: (body: Partial<Profile>) => request<Profile>('/profiles', json(body)),
  updateProfile: (id: string, body: Partial<Profile>) =>
    request<Profile>(`/profiles/${id}`, json(body, 'PATCH')),

  createTemplate: (caseId: string, profileIds: string[], materialIds: string[]) =>
    request<Workflow>('/workflows/template', json({ case_id: caseId, profile_ids: profileIds, material_ids: materialIds })),
  getWorkflow: (id: string) => request<Workflow>(`/workflows/${id}`),
  updateWorkflow: (id: string, definition: WorkflowDefinition) =>
    request<Workflow>(`/workflows/${id}`, json(definition, 'PUT')),
  preview: (caseId: string, workflow: WorkflowDefinition) =>
    request<{ steps: PreviewStep[] }>('/workflows/preview', json({ case_id: caseId, workflow })),

  startRun: (caseId: string, workflowId: string) =>
    request<RunDetail>('/runs', json({ case_id: caseId, workflow_id: workflowId })),
  getRun: (id: string) => request<RunDetail>(`/runs/${id}`),
  listRuns: (caseId: string) => request<RunSummary[]>(`/runs?case_id=${caseId}`),
  decide: (runId: string, stepId: string, text: string) =>
    request<RunDetail>(`/runs/${runId}/decision`, json({ step_id: stepId, text })),

  lastDecision: (run: RunDetail): Decision | null => run.decisions[run.decisions.length - 1] ?? null,
}
