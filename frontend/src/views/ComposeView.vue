<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { VueFlow } from '@vue-flow/core'
import type { Edge as FlowEdge, Node as FlowNode, NodeDragEvent, NodeMouseEvent } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { api } from '../api'
import type { Material, PreviewStep, Profile, Step, Workflow, WorkflowDefinition } from '../types'

const props = defineProps<{
  caseId: string
  materials: Material[]
  profiles: Profile[]
  workflow: Workflow | null
}>()

const emit = defineEmits<{
  (event: 'run'): void
  (event: 'saved', workflow: Workflow): void
  (event: 'open-run', runId: string): void
  (event: 'error', message: string): void
  (event: 'profiles-changed', profiles: Profile[]): void
}>()

const definition = ref<WorkflowDefinition | null>(
  props.workflow ? JSON.parse(JSON.stringify(props.workflow.definition)) : null,
)
const selectedId = ref('')
const preview = ref<PreviewStep[] | null>(null)
const localProfiles = ref<Profile[]>([...props.profiles])
const dirty = ref(false)

watch(
  () => props.workflow,
  (next) => {
    if (next) definition.value = JSON.parse(JSON.stringify(next.definition))
  },
)

watch(
  () => props.profiles,
  (next) => {
    if (next.length) localProfiles.value = [...next]
  },
)

const steps = computed<Step[]>(() => definition.value?.steps ?? [])
const selected = computed<Step | null>(() => steps.value.find((step) => step.id === selectedId.value) ?? null)

function profileName(profileId: string | null): string {
  if (!profileId) return 'no profile'
  return localProfiles.value.find((profile) => profile.id === profileId)?.name ?? 'unknown profile'
}

const nodes = computed<FlowNode[]>(() =>
  steps.value.map((step) => ({
    id: step.id,
    type: 'mread',
    position: { x: step.position.x, y: step.position.y },
    data: {
      label: step.name,
      kind: step.kind,
      profile: profileName(step.profile_id),
      materials: step.material_ids.length,
      empty: step.kind === 'agent' && step.material_ids.length === 0,
      current: step.id === selectedId.value,
    },
  })),
)

const edges = computed<FlowEdge[]>(() =>
  (definition.value?.edges ?? []).map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: 'smoothstep',
    label: edge.passes_output ? 'passes output' : 'no output',
    style: { stroke: '#477575' },
    labelStyle: { fill: '#6b7472', fontSize: '11px' },
  })),
)

function onNodeClick(event: NodeMouseEvent) {
  selectedId.value = event.node.id
  preview.value = null
}

function onNodeDragStop(event: NodeDragEvent) {
  const step = steps.value.find((item) => item.id === event.node.id)
  if (!step) return
  step.position = { x: Math.round(event.node.position.x), y: Math.round(event.node.position.y) }
  dirty.value = true
}

function nextStepId(): string {
  let index = steps.value.length + 1
  while (steps.value.some((step) => step.id === `step${index}`)) index += 1
  return `step${index}`
}

function addStep(kind: 'agent' | 'human') {
  if (!definition.value) return
  const last = steps.value[steps.value.length - 1]
  const id = nextStepId()
  const profile = kind === 'agent' ? localProfiles.value[0]?.id ?? null : null
  if (kind === 'agent' && !profile) {
    emit('error', 'create an agent profile first')
    return
  }
  definition.value.steps.push({
    id,
    name: kind === 'human' ? 'Researcher step' : `Step ${steps.value.length + 1}`,
    kind,
    profile_id: profile,
    material_ids: [],
    human_prompt: kind === 'human' ? 'What should the reading answer next?' : '',
    position: { x: last ? last.position.x + 260 : 0, y: last ? last.position.y : 0 },
  })
  if (last && !definition.value.edges.some((edge) => edge.source === last.id)) {
    definition.value.edges.push({
      id: `edge${definition.value.edges.length + 1}-${id}`,
      source: last.id,
      target: id,
      passes_output: true,
    })
  }
  selectedId.value = id
  dirty.value = true
}

function removeStep(stepId: string) {
  if (!definition.value) return
  definition.value.steps = definition.value.steps.filter((step) => step.id !== stepId)
  definition.value.edges = definition.value.edges.filter(
    (edge) => edge.source !== stepId && edge.target !== stepId,
  )
  if (selectedId.value === stepId) selectedId.value = ''
  dirty.value = true
}

function toggleMaterial(step: Step, materialId: string) {
  const index = step.material_ids.indexOf(materialId)
  if (index >= 0) step.material_ids.splice(index, 1)
  else step.material_ids.push(materialId)
  dirty.value = true
}

async function save(): Promise<boolean> {
  if (!definition.value || !props.workflow) return false
  try {
    const saved = await api.updateWorkflow(props.workflow.id, definition.value)
    emit('saved', saved)
    dirty.value = false
    return true
  } catch (err) {
    emit('error', (err as Error).message)
    return false
  }
}

async function showPreview() {
  if (!definition.value) return
  try {
    const result = await api.preview(props.caseId, definition.value)
    preview.value = result.steps
  } catch (err) {
    emit('error', (err as Error).message)
  }
}

async function startRun() {
  if (dirty.value) {
    const ok = await save()
    if (!ok) return
  }
  emit('run')
}

async function createStartingWorkflow() {
  if (!props.caseId || props.workflow) return
  try {
    const seeded = localProfiles.value.length ? localProfiles.value : await api.seedProfiles()
    localProfiles.value = seeded
    emit('profiles-changed', seeded)
    const created = await api.createTemplate(
      props.caseId,
      seeded.map((profile) => profile.id),
      props.materials.map((material) => material.id),
    )
    definition.value = JSON.parse(JSON.stringify(created.definition))
    emit('saved', created)
  } catch (err) {
    emit('error', (err as Error).message)
  }
}

onMounted(createStartingWorkflow)

// ------------------------------------------------------------------ profile editing

const editingProfileId = ref('')
const draft = ref<Profile | null>(null)

function editProfile(profileId: string) {
  editingProfileId.value = profileId
  const found = localProfiles.value.find((profile) => profile.id === profileId)
  draft.value = found ? { ...found } : null
}

async function saveProfile() {
  if (!draft.value) return
  try {
    const updated = await api.updateProfile(draft.value.id, draft.value)
    localProfiles.value = localProfiles.value.map((profile) =>
      profile.id === updated.id ? updated : profile,
    )
    emit('profiles-changed', localProfiles.value)
    draft.value = { ...updated }
    emit('error', '')
  } catch (err) {
    emit('error', (err as Error).message)
  }
}

async function createProfile() {
  try {
    const created = await api.createProfile({
      name: 'New agent',
      role_instructions: 'Describe the task this agent performs, and what it must not claim.',
      model: '',
      expected_response: '',
    })
    localProfiles.value = [...localProfiles.value, created]
    emit('profiles-changed', localProfiles.value)
    editProfile(created.id)
  } catch (err) {
    emit('error', (err as Error).message)
  }
}
</script>

<template>
  <div v-if="definition" class="split" style="grid-template-columns: minmax(0, 1fr) 420px">
    <section style="position: relative; min-height: 0; background: #e9ebe5">
      <div class="row toolbar">
        <button @click="addStep('agent')">+ Agent step</button>
        <button @click="addStep('human')">+ Human step</button>
        <button :disabled="!dirty" @click="save">Save workflow</button>
        <button @click="showPreview">Preview inputs</button>
        <button class="primary" @click="startRun">Run</button>
        <span v-if="dirty" class="hint">unsaved changes</span>
        <span v-else class="hint">workflow v{{ workflow?.version }}</span>
      </div>
      <div style="position: absolute; inset: 44px 0 0 0">
        <VueFlow
          :nodes="nodes"
          :edges="edges"
          :min-zoom="0.3"
          :max-zoom="1.6"
          fit-view-on-init
          @node-click="onNodeClick"
          @node-drag-stop="onNodeDragStop"
        >
          <template #node-mread="{ data }">
            <div class="step-node" :class="[data.kind, { current: data.current, empty: data.empty }]">
              <strong>{{ data.label }}</strong>
              <div class="small">{{ data.kind === 'human' ? 'human step' : data.profile }}</div>
              <div class="small">
                {{ data.materials }} material(s)
                <template v-if="data.empty"> · no material</template>
              </div>
            </div>
          </template>
        </VueFlow>
      </div>
    </section>

    <aside class="pane" style="border-left: 1px solid var(--line); background: #fafbf8">
      <h2>Step</h2>
      <div v-if="selected" class="card">
        <label class="field">
          <span>Name</span>
          <input v-model="selected.name" @input="dirty = true" />
        </label>
        <div class="row" style="margin-bottom: 10px">
          <span class="tag" :class="selected.kind">{{ selected.kind }}</span>
          <button class="danger ghost" @click="removeStep(selected.id)">Remove step</button>
        </div>

        <template v-if="selected.kind === 'agent'">
          <label class="field">
            <span>Agent profile</span>
            <select v-model="selected.profile_id" @change="dirty = true">
              <option v-for="profile in localProfiles" :key="profile.id" :value="profile.id">
                {{ profile.name }}
              </option>
            </select>
          </label>
        </template>
        <label v-else class="field">
          <span>Prompt for the researcher</span>
          <textarea v-model="selected.human_prompt" rows="3" @input="dirty = true"></textarea>
        </label>

        <span class="field" style="display: block; margin-bottom: 10px">
          <span style="display: block; font-size: 12px; text-transform: uppercase; color: var(--muted)">
            Materials bound to this step
          </span>
          <label v-for="material in materials" :key="material.id" style="display: flex; gap: 8px; align-items: center; margin-top: 6px">
            <input
              type="checkbox"
              style="width: auto"
              :checked="selected.material_ids.includes(material.id)"
              @change="toggleMaterial(selected, material.id)"
            />
            <span class="tag">{{ material.kind }}</span>
            <span>{{ material.title || material.id }}</span>
          </label>
          <p v-if="materials.length === 0" class="empty">No materials in this case.</p>
          <p
            v-if="selected.kind === 'agent' && selected.material_ids.length === 0"
            class="hint"
            style="color: var(--danger)"
          >
            This step has no material bound, so a run will be refused. Bind an image or article
            above, or remove the step.
          </p>
        </span>
      </div>
      <p v-else class="hint">Select a step on the canvas to edit what it receives.</p>

      <h2 style="margin-top: 18px">Agent profiles</h2>
      <ul class="material-list">
        <li v-for="profile in localProfiles" :key="profile.id">
          <button class="ghost" @click="editProfile(profile.id)">Edit</button>
          <span style="flex: 1">{{ profile.name }}</span>
          <span class="id">v{{ profile.version }}</span>
        </li>
      </ul>
      <button style="margin-top: 8px" @click="createProfile">+ New profile</button>

      <div v-if="draft" class="card" style="margin-top: 12px">
        <h3>{{ draft.name }}</h3>
        <label class="field">
          <span>Name</span>
          <input v-model="draft.name" />
        </label>
        <label class="field">
          <span>Role instructions</span>
          <textarea v-model="draft.role_instructions" rows="6"></textarea>
        </label>
        <label class="field">
          <span>Expected response (optional)</span>
          <input v-model="draft.expected_response" />
        </label>
        <label class="field">
          <span>Model (blank uses the server default)</span>
          <input v-model="draft.model" placeholder="e.g. deepseek-chat" />
        </label>
        <button class="primary" @click="saveProfile">Save profile</button>
        <p class="hint">Saving a profile does not change runs that already started.</p>
      </div>

      <div v-if="preview" style="margin-top: 18px">
        <h2>What each step will receive</h2>
        <table style="width: 100%; border-collapse: collapse; font-size: 12.5px">
          <thead>
            <tr>
              <th style="text-align: left; padding: 4px">Step</th>
              <th style="text-align: left; padding: 4px">Materials</th>
              <th style="text-align: left; padding: 4px">Prior steps</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in preview" :key="item.step_id">
              <td style="padding: 4px">{{ item.step_name }}</td>
              <td style="padding: 4px">{{ item.material_ids.length }} ({{ item.material_ids.join(', ') }})</td>
              <td style="padding: 4px">{{ item.prior_step_ids.join(', ') || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </aside>
  </div>
  <div v-else class="pane">
    <p class="empty">Choose a case in Prepare first; a starting workflow is created for you.</p>
  </div>
</template>

<style scoped>
.toolbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 44px;
  padding: 6px 12px;
  background: rgba(241, 242, 238, 0.94);
  border-bottom: 1px solid var(--line);
  z-index: 3;
}

.step-node {
  background: #fff;
  border: 1px solid var(--line);
  border-left: 3px solid var(--active);
  border-radius: 3px;
  padding: 8px 10px;
  min-width: 170px;
  box-shadow: 0 1px 2px rgba(28, 41, 46, 0.08);
  color: var(--text);
}

.step-node.human {
  border-left-color: var(--ref);
}

.step-node.empty {
  border-left-color: var(--danger);
}

.step-node.current {
  outline: 2px solid var(--active);
}

.step-node .small {
  font-size: 11.5px;
  color: var(--muted);
}
</style>
