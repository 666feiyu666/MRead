<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from './api'
import type { Case, Material, Profile, RunDetail, RuntimeConfig, Workflow } from './types'
import PrepareView from './views/PrepareView.vue'
import ComposeView from './views/ComposeView.vue'
import ReadView from './views/ReadView.vue'

const view = ref<'prepare' | 'compose' | 'read'>('prepare')
const cases = ref<Case[]>([])
const activeCase = ref<Case | null>(null)
const materials = ref<Material[]>([])
const profiles = ref<Profile[]>([])
const workflow = ref<Workflow | null>(null)
const runId = ref('')
const run = ref<RunDetail | null>(null)
const config = ref<RuntimeConfig | null>(null)
const error = ref('')

function store() {
  const state = {
    caseId: activeCase.value?.id ?? '',
    workflowId: workflow.value?.id ?? '',
    runId: runId.value,
    view: view.value,
  }
  localStorage.setItem('mread.state', JSON.stringify(state))
}

async function loadCases() {
  cases.value = await api.listCases()
}

async function selectCase(caseId: string) {
  error.value = ''
  try {
    const detail = await api.getCase(caseId)
    activeCase.value = { ...detail }
    materials.value = detail.assets ?? []
    profiles.value = await api.listProfiles()
    if (!profiles.value.length) profiles.value = await api.seedProfiles()
    const workflows = detail.workflows ?? []
    workflow.value = workflows.length ? workflows[workflows.length - 1] : null
    store()
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function refreshCase() {
  if (activeCase.value) await selectCase(activeCase.value.id)
}

async function startRun() {
  if (!activeCase.value || !workflow.value) return
  error.value = ''
  try {
    const detail = await api.startRun(activeCase.value.id, workflow.value.id)
    run.value = detail
    runId.value = detail.run.id
    view.value = 'read'
    store()
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function openRun(id: string) {
  runId.value = id
  view.value = 'read'
  store()
}

onMounted(async () => {
  try {
    config.value = await api.runtimeConfig()
    await loadCases()
  } catch (err) {
    error.value = (err as Error).message
  }
  const saved = localStorage.getItem('mread.state')
  if (!saved) return
  let state: { caseId?: string; workflowId?: string; runId?: string; view?: string } = {}
  try {
    state = JSON.parse(saved)
  } catch {
    localStorage.removeItem('mread.state')
    return
  }

  if (state.caseId) await selectCase(state.caseId)

  // A stored run may point at data that no longer exists (deleted database, other
  // working copy). Verify it before restoring the read view instead of showing an empty one.
  let restoredRun = false
  if (state.runId) {
    try {
      run.value = await api.getRun(state.runId)
      runId.value = state.runId
      restoredRun = true
    } catch {
      run.value = null
      runId.value = ''
    }
  }

  if (restoredRun && state.view === 'read') view.value = 'read'
  else if (activeCase.value) view.value = state.view === 'compose' ? 'compose' : 'prepare'
  else view.value = 'prepare'

  if (!restoredRun && state.runId) error.value = ''
  store()
})
</script>

<template>
  <div class="app">
    <header class="topbar">
      <h1>MRead</h1>
      <span v-if="activeCase" class="case-title">{{ activeCase.title }}</span>
      <span v-if="run" class="status" :class="run.run.status">{{ run.run.status }}</span>
      <span v-if="config" class="status" :title="config.data_dir">
        {{ config.provider }} · {{ config.data_profile }}<template v-if="!config.image_input"> · text only</template>
      </span>
      <nav class="tabs">
        <button :class="{ active: view === 'prepare' }" @click="view = 'prepare'">1 · Prepare</button>
        <button :class="{ active: view === 'compose' }" :disabled="!activeCase" @click="view = 'compose'">
          2 · Compose
        </button>
        <button :class="{ active: view === 'read' }" :disabled="!runId" @click="view = 'read'">3 · Read</button>
      </nav>
    </header>

    <div v-if="error" class="error" style="margin: 12px 18px">{{ error }}</div>

    <div class="main">
      <PrepareView
        v-if="view === 'prepare'"
        :cases="cases"
        :active-case="activeCase"
        :materials="materials"
        @refresh-cases="loadCases"
        @select-case="selectCase"
        @materials-changed="refreshCase"
        @error="(message: string) => (error = message)"
        @continue="view = 'compose'"
      />
      <ComposeView
        v-else-if="view === 'compose'"
        :case-id="activeCase?.id ?? ''"
        :materials="materials"
        :profiles="profiles"
        :workflow="workflow"
        @run="startRun"
        @saved="(saved: Workflow) => { workflow = saved; store() }"
        @open-run="openRun"
        @error="(message: string) => (error = message)"
        @profiles-changed="(next: Profile[]) => (profiles = next)"
      />
      <ReadView
        v-else
        :run-id="runId"
        :materials="materials"
        @error="(message: string) => (error = message)"
        @updated="(detail: RunDetail) => (run = detail)"
        @back="view = 'compose'"
      />
    </div>
  </div>
</template>
