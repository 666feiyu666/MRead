<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import type { Evidence, Material, MaterialDetail, RunDetail, StepRecord } from '../types'

const props = defineProps<{
  runId: string
  materials: Material[]
}>()

const emit = defineEmits<{
  (event: 'error', message: string): void
  (event: 'updated', detail: RunDetail): void
  (event: 'back'): void
}>()

const detail = ref<RunDetail | null>(null)
const activeMaterialId = ref('')
const materialDetail = ref<MaterialDetail | null>(null)
const zoom = ref(1)
const highlight = ref<Evidence | null>(null)
const decisionText = ref('')
const submitting = ref(false)
const referenceText = ref('')

let timer: number | undefined

async function load() {
  if (!props.runId) return
  try {
    const body = await api.getRun(props.runId)
    detail.value = body
    emit('updated', body)
    if (!activeMaterialId.value) {
      const firstImage = props.materials.find((material) => material.kind === 'image')
      if (firstImage) await showMaterial(firstImage.id)
    }
    schedulePoll()
  } catch (err) {
    emit('error', (err as Error).message)
  }
}

function schedulePoll() {
  window.clearTimeout(timer)
  const status = detail.value?.run.status
  if (status === 'queued' || status === 'running') {
    timer = window.setTimeout(load, 1500)
  }
}

async function showMaterial(materialId: string) {
  activeMaterialId.value = materialId
  try {
    materialDetail.value = await api.material(materialId)
  } catch (err) {
    emit('error', (err as Error).message)
  }
}

async function focusEvidence(item: Evidence) {
  highlight.value = item
  referenceText.value = item.text
  if (!item.asset_id) return
  if (item.asset_id !== activeMaterialId.value) await showMaterial(item.asset_id)
  if (!item.region && !item.passage) return
}

const recordList = computed<StepRecord[]>(() =>
  (detail.value?.records ?? []).map((record) => ({
    ...record,
    payload: {
      ...(record.payload ?? {}),
      step_id: record.payload?.step_id ?? record.step_id,
      step_name: record.payload?.step_name ?? record.step_name,
      kind: record.payload?.kind ?? record.kind,
      material_ids: record.payload?.material_ids ?? [],
      prior_step_ids: record.payload?.prior_step_ids ?? [],
    } as StepRecord['payload'],
    output: record.output ?? {},
  })),
)
const awaiting = computed(() => detail.value?.awaiting ?? null)
const isImage = computed(() => materialDetail.value?.kind === 'image')
const imageUrl = computed(() =>
  activeMaterialId.value ? `/api/assets/${activeMaterialId.value}/content` : '',
)

const passageParts = computed(() => {
  const text = materialDetail.value?.text ?? ''
  const passage = highlight.value?.passage
  if (!passage || passage.start >= text.length) return { before: text, hit: '', after: '' }
  const start = Math.max(0, passage.start)
  const end = Math.min(text.length, Math.max(start, passage.end))
  return {
    before: text.slice(0, start),
    hit: text.slice(start, end),
    after: text.slice(end),
  }
})

function statusLabel(record: StepRecord): string {
  return record.status.replace('_', ' ')
}

async function submitDecision() {  const stepId = awaiting.value?.step_id
  if (!stepId || !decisionText.value.trim()) return
  submitting.value = true
  try {
    const body = await api.decide(props.runId, stepId, decisionText.value.trim())
    detail.value = body
    emit('updated', body)
    decisionText.value = ''
    schedulePoll()
  } catch (err) {
    emit('error', (err as Error).message)
    await load()
  } finally {
    submitting.value = false
  }
}

function onClearHighlight() {
  referenceText.value = ''
  highlight.value = null
}

watch(() => props.runId, load)

onMounted(load)
onBeforeUnmount(() => window.clearTimeout(timer))
</script>

<template>
  <div class="split" style="grid-template-columns: minmax(0, 1fr) 480px">
    <section class="pane" style="background: var(--ink); color: #eef1ee">
      <div class="row" style="margin-bottom: 10px">
        <button class="ghost" style="color: #eef1ee; border-color: #4a5f66" @click="emit('back')">← Compose</button>
        <span v-if="materialDetail" class="tag" style="border-color: #4a5f66; color: #cfd8d3">
          {{ materialDetail.kind }}
        </span>
        <strong v-if="materialDetail" style="font-family: var(--serif)">
          {{ materialDetail.title }}
        </strong>
        <span style="margin-left: auto"></span>
        <template v-if="isImage">
          <button class="ghost" style="color: #eef1ee; border-color: #4a5f66" @click="zoom = Math.max(0.4, zoom - 0.2)">−</button>
          <span class="hint" style="color: #cfd8d3">{{ Math.round(zoom * 100) }}%</span>
          <button class="ghost" style="color: #eef1ee; border-color: #4a5f66" @click="zoom = Math.min(4, zoom + 0.2)">+</button>
          <button class="ghost" style="color: #eef1ee; border-color: #4a5f66" @click="zoom = 1">Reset</button>
        </template>
      </div>

      <div class="row" style="margin-bottom: 10px">
        <button
          v-for="material in materials"
          :key="material.id"
          class="ghost"
          :style="{
            color: material.id === activeMaterialId ? '#fff' : '#cfd8d3',
            borderColor: material.id === activeMaterialId ? '#477575' : '#4a5f66',
          }"
          @click="showMaterial(material.id)"
        >
          {{ material.kind === 'image' ? 'Image' : 'Article' }} · {{ material.title || material.id }}
        </button>
      </div>

      <div v-if="materialDetail?.provenance" class="hint" style="color: #a9b8b4; margin-bottom: 10px">
        {{ materialDetail.provenance }}
      </div>

      <div v-if="isImage" style="overflow: auto; max-height: calc(100vh - 210px)">
        <div
          class="image-stage"
          :style="{ transform: `scale(${zoom})`, transformOrigin: 'top left' }"
        >
          <img :src="imageUrl" :alt="materialDetail?.title ?? 'uploaded image'" />
          <div
            v-if="highlight?.region"
            class="region"
            :style="{
              left: `${highlight.region.x * 100}%`,
              top: `${highlight.region.y * 100}%`,
              width: `${highlight.region.width * 100}%`,
              height: `${highlight.region.height * 100}%`,
            }"
          ></div>
        </div>
        <p class="hint" style="color: #a9b8b4">
          Only this frame is visible to the agents. Regions come from their claims, not from the
          interface guessing.
        </p>
      </div>

      <div v-else-if="materialDetail" class="reading-surface">
        <p class="article-body">
          <span>{{ passageParts.before }}</span><mark v-if="passageParts.hit">{{ passageParts.hit }}</mark><span>{{ passageParts.after }}</span>
        </p>
      </div>
      <p v-else class="hint" style="color: #a9b8b4">Choose a material to inspect it.</p>
    </section>

    <aside class="pane" style="border-left: 1px solid var(--line); background: #fafbf8">
      <div class="row">
        <h2 style="flex: 1">Exchange</h2>
        <span class="status" :class="detail?.run.status">{{ detail?.run.status }}</span>
      </div>
      <p v-if="detail?.run.error" class="error">{{ detail.run.error }}</p>

      <div v-if="referenceText" class="card" style="border-left: 3px solid var(--ref)">
        <h3>Claim under inspection</h3>
        <p>{{ referenceText }}</p>
        <button class="ghost" @click="onClearHighlight">Clear</button>
      </div>

      <div v-for="record in recordList" :key="record.id" class="card">
        <div class="row">
          <strong style="flex: 1">{{ record.step_name }}</strong>
          <span class="tag" :class="record.status">{{ statusLabel(record) }}</span>
        </div>
        <p class="hint">
          {{ record.kind === 'human' ? 'human step' : record.payload.model }}
          · materials {{ record.payload.material_ids.length }}
          · prior steps {{ record.payload.prior_step_ids.join(', ') || '—' }}
        </p>

        <p v-if="record.error" class="error">{{ record.error }}</p>

        <template v-if="record.output?.note">
          <p class="note">{{ record.output.note }}</p>
        </template>

        <ul v-if="record.output?.evidence?.length" class="evidence-list">
          <li v-for="item in record.output.evidence" :key="item.id">
            <button class="ghost evidence" @click="focusEvidence(item)">
              <span class="tag" :class="item.type">{{ item.type.replace('_', ' ') }}</span>
              <span>{{ item.text }}</span>
            </button>
            <div class="hint">
              {{ item.asset_id ?? 'no material' }}
              <template v-if="item.passage">
                · characters {{ item.passage.start }}–{{ item.passage.end }}
              </template>
              <template v-if="item.region">
                · region {{ Math.round(item.region.x * 100) }}%, {{ Math.round(item.region.y * 100) }}%
              </template>
            </div>
          </li>
        </ul>

        <div v-if="record.output?.unresolved?.length" class="unresolved">
          <h3>Still open</h3>
          <ul>
            <li v-for="line in record.output.unresolved" :key="line">{{ line }}</li>
          </ul>
        </div>

        <div v-if="record.output?.rejected?.length" class="rejected">
          <h3>Rejected by validation</h3>
          <ul>
            <li v-for="(item, index) in record.output.rejected" :key="index">
              <span class="tag question">{{ item.type.replace('_', ' ') }}</span>
              <span>{{ item.text }}</span>
              <div class="hint">{{ item.reason }}</div>
            </li>
          </ul>
        </div>
      </div>

      <div v-if="awaiting" class="card" style="border-left: 3px solid var(--ref)">
        <h3>{{ awaiting.step_name }}</h3>
        <p class="hint">{{ awaiting.human_prompt }}</p>
        <textarea v-model="decisionText" rows="4" placeholder="One question or decision"></textarea>
        <p class="hint">Recorded once. Later outputs are appended; earlier readings are not rewritten.</p>
        <button class="primary" :disabled="submitting || !decisionText.trim()" @click="submitDecision">
          Submit decision
        </button>
      </div>
    </aside>
  </div>
</template>

<script lang="ts">
export default {
  methods: {
    onClearHighlight(this: { referenceText: string; highlight: unknown }) {
      this.referenceText = ''
      this.highlight = null
    },
  },
}
</script>

<style scoped>
.image-stage {
  position: relative;
  display: inline-block;
  background: #1b2a30;
}

.image-stage img {
  display: block;
  max-width: 100%;
  height: auto;
}

.region {
  position: absolute;
  border: 2px solid var(--ref);
  box-shadow: 0 0 0 9999px rgba(28, 41, 46, 0.28);
  pointer-events: none;
}

.reading-surface {
  background: var(--paper);
  color: var(--text);
  padding: 18px 20px;
  border-radius: 3px;
  max-height: calc(100vh - 210px);
  overflow: auto;
}

.article-body {
  white-space: pre-wrap;
  font-family: var(--serif);
  font-size: 15px;
  line-height: 1.7;
}

.article-body mark {
  background: #f0dfc4;
  outline: 1px solid var(--ref);
}

.note {
  white-space: pre-wrap;
}

.evidence-list {
  list-style: none;
  padding: 0;
  margin: 8px 0 0;
}

.evidence-list li {
  margin-bottom: 8px;
}

.evidence {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  text-align: left;
  width: 100%;
  background: #f5f6f2;
  border-color: transparent;
  padding: 6px 8px;
}

.evidence:hover {
  border-color: var(--ref);
}

.unresolved {
  margin-top: 10px;
  border-top: 1px dashed var(--line);
  padding-top: 8px;
}

.unresolved ul {
  margin: 4px 0 0;
  padding-left: 18px;
  color: var(--muted);
}

.rejected {
  margin-top: 10px;
  border-top: 1px dashed #d9c3bf;
  padding-top: 8px;
}

.rejected ul {
  margin: 4px 0 0;
  padding-left: 0;
  list-style: none;
}

.rejected li {
  border-left: 2px solid var(--danger);
  padding-left: 8px;
  margin-bottom: 8px;
  color: #5b4a47;
}

.rejected .hint {
  color: var(--danger);
}
</style>
