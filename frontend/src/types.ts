export type AssetKind = 'image' | 'article' | 'note'
export type StepKind = 'agent' | 'human'
export type RecordStatus = 'pending' | 'running' | 'completed' | 'awaiting_human' | 'failed' | 'skipped'

export interface Case {
  id: string
  title: string
  notes: string
  created_at: string
}

export interface Material {
  id: string
  case_id: string
  kind: AssetKind
  title: string
  provenance: string
  mime: string
  size: number
  created_at: string
}

export interface MaterialDetail extends Material {
  text: string
}

export interface MaterialReference {
  workflow_id: string
  workflow_name: string
  workflow_version: number
  step_id: string
  step_name: string
}

export interface MaterialListing extends Material {
  text_chars: number
  references: {
    workflows: MaterialReference[]
    runs: number
  }
}

export interface Profile {
  id: string
  name: string
  role_instructions: string
  model: string
  expected_response: string
  version: number
}

export interface Step {
  id: string
  name: string
  kind: StepKind
  profile_id: string | null
  material_ids: string[]
  human_prompt: string
  position: { x: number; y: number }
}

export interface Edge {
  id: string
  source: string
  target: string
  passes_output: boolean
}

export interface WorkflowDefinition {
  name: string
  case_id: string
  steps: Step[]
  edges: Edge[]
}

export interface Workflow {
  id: string
  case_id: string
  name: string
  version: number
  definition: WorkflowDefinition
  created_at: string
  updated_at: string
}

export interface Region {
  x: number
  y: number
  width: number
  height: number
}

export interface Passage {
  start: number
  end: number
}

export interface Evidence {
  id: string
  type: 'observation' | 'source_report' | 'interpretation' | 'question'
  text: string
  asset_id: string | null
  region: Region | null
  passage: Passage | null
  refers_to: string[]
}

export interface StepPayload {
  step_id: string
  step_name: string
  kind: StepKind
  profile_id?: string | null
  profile_name?: string | null
  model?: string
  material_ids: string[]
  prior_step_ids: string[]
  human_prompt?: string
  human_decision?: { step_id: string; text: string } | null
  materials?: Array<{ asset_id: string; kind: string; title: string; text_chars: number }>
  image_parts_sent?: number
}

export interface RejectedEvidence {
  type: string
  text: string
  reason: string
}

export interface StepOutput {
  note?: string
  evidence?: Evidence[]
  unresolved?: string[]
  rejected?: RejectedEvidence[]
  decision_id?: string
}

export interface StepRecord {
  id: string
  run_id: string
  step_id: string
  step_name: string
  kind: StepKind
  ordinal: number
  status: RecordStatus
  payload: StepPayload
  output: StepOutput
  error: string
  started_at: string
  finished_at: string
}

export interface RunSummary {
  id: string
  case_id: string
  workflow_id: string
  workflow_version: number
  status: 'queued' | 'running' | 'awaiting_human' | 'completed' | 'failed'
  provider: string
  error: string
  created_at: string
  updated_at: string
}

export interface Decision {
  id: string
  run_id: string
  step_id: string
  text: string
  created_at: string
}

export interface RunDetail {
  run: RunSummary
  snapshot: {
    case: { id: string; title: string }
    workflow: { id: string; name: string; version: number }
    profiles: Record<string, Profile>
    material_ids: string[]
    plan: Array<{ step: Step; ordinal: number; upstream: string[] }>
  }
  records: StepRecord[]
  decisions: Decision[]
  awaiting: { step_id: string; step_name: string; human_prompt: string } | null
  case: Case
}

export interface PreviewStep {
  step_id: string
  step_name: string
  kind: StepKind
  profile_id: string | null
  material_ids: string[]
  materials: Array<{ asset_id: string; kind: string }>
  prior_step_ids: string[]
}

export interface RuntimeConfig {
  provider: string
  default_model: string
  key_configured: boolean
  base_url_host: string
  image_input: boolean
  data_profile: string
  data_dir: string
}
