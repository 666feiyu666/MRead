<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import type { MaterialDetail, MaterialListing } from '../types'

const props = defineProps<{
  caseId: string
}>()

const emit = defineEmits<{
  (event: 'changed'): void
  (event: 'error', message: string): void
}>()

const items = ref<MaterialListing[]>([])
const selectedId = ref('')
const detail = ref<MaterialDetail | null>(null)
const query = ref('')
const zoom = ref(1)
const busy = ref(false)
const confirmingDelete = ref(false)

const titleDraft = ref('')
const provenanceDraft = ref('')

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return items.value
  return items.value.filter(
    (item) =>
      item.title.toLowerCase().includes(needle) ||
      item.id.toLowerCase().includes(needle) ||
      item.kind.includes(needle),
  )
})

const selected = computed(() => items.value.find((item) => item.id === selectedId.value) ?? null)
const isImage = computed(() => detail.value?.kind === 'image')
const imageUrl = computed(() => (selectedId.value ? `/api/assets/${selectedId.value}/content` : ''))

async function load(keepSelection = true) {
  if (!props.caseId) return
  try {
    const body = await api.materials(props.caseId)
    items.value = body.assets
    if (!keepSelection || !items.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = items.value[0]?.id ?? ''
    }
    if (selectedId.value) await open(selectedId.value)
    else detail.value = null
  } catch (err) {
    emit('error', (err as Error).message)
  }
}

async function open(materialId: string) {
  selectedId.value = materialId
  confirmingDelete.value = false
  zoom.value = 1
  try {
    detail.value = await api.material(materialId)
    titleDraft.value = detail.value.title
    provenanceDraft.value = detail.value.provenance
  } catch (err) {
    emit('error', (err as Error).message)
  }
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const dirty = computed(
  () =>
    !!detail.value &&
    (titleDraft.value !== detail.value.title || provenanceDraft.value !== detail.value.provenance),
)

async function saveMeta() {
  if (!detail.value) return
  busy.value = true
  try {
    await api.renameMaterial(detail.value.id, {
      title: titleDraft.value,
      provenance: provenanceDraft.value,
    })
    await load()
    emit('changed')
  } catch (err) {
    emit('error', (err as Error).message)
  } finally {
    busy.value = false
  }
}

async function removeSelected() {
  if (!detail.value) return
  if (!confirmingDelete.value) {
    confirmingDelete.value = true
    return
  }
  busy.value = true
  try {
    const result = await api.deleteMaterial(detail.value.id)
    const steps = result.unbound_from.map((entry) => entry.step_name).join(', ')
    emit(
      'error',
      steps
        ? `Deleted ${result.deleted}. Unbound from: ${steps}.`
        : `Deleted ${result.deleted}.`,
    )
    selectedId.value = ''
    detail.value = null
    confirmingDelete.value = false
    await load(false)
    emit('changed')
  } catch (err) {
    emit('error', (err as Error).message)
  } finally {
    busy.value = false
  }
}

watch(() => props.caseId, () => load(false))
onMounted(() => load(false))
</script>

<template>
  <div class="split" style="grid-template-columns: 380px minmax(0, 1fr)">
    <aside class="pane" style="border-right: 1px solid var(--line); background: #fafbf8">
      <h2>Materials</h2>
      <p class="hint">
        Everything uploaded to this case. Each row is a row in the case database; the image or
        text beside it is the file the agents actually receive.
      </p>
      <input v-model="query" placeholder="Filter by title, kind, or id" style="margin-bottom: 10px" />

      <ul v-if="filtered.length" class="material-list">
        <li
          v-for="item in filtered"
          :key="item.id"
          :style="{ background: item.id === selectedId ? '#eef1ec' : 'transparent', cursor: 'pointer' }"
          @click="open(item.id)"
        >
          <span class="tag">{{ item.kind }}</span>
          <span style="flex: 1">{{ item.title || item.id }}</span>
          <span class="hint">
            <template v-if="item.references.workflows.length">
              {{ item.references.workflows.length }} step(s)
            </template>
            <template v-else>unbound</template>
          </span>
        </li>
      </ul>
      <p v-else-if="items.length" class="empty">Nothing matches that filter.</p>
      <p v-else class="empty">No materials in this case yet.</p>
    </aside>

    <section class="pane">
      <div v-if="detail">
        <div class="row" style="margin-bottom: 10px">
          <h2 style="flex: 1">{{ detail.kind === 'image' ? 'Image' : 'Text' }}</h2>
          <template v-if="isImage">
            <button @click="zoom = Math.max(0.2, zoom - 0.2)">−</button>
            <span class="hint">{{ Math.round(zoom * 100) }}%</span>
            <button @click="zoom = Math.min(4, zoom + 0.2)">+</button>
            <button @click="zoom = 1">Reset</button>
          </template>
        </div>

        <div v-if="isImage" class="preview-mount">
          <img
            :src="imageUrl"
            :alt="detail.title"
            :style="{ transform: `scale(${zoom})`, transformOrigin: 'top left' }"
          />
        </div>
        <div v-else class="preview-text">
          <pre>{{ detail.text }}</pre>
        </div>

        <div class="card" style="margin-top: 14px">
          <h3>Record</h3>
          <table class="meta">
            <tbody>
              <tr><th>id</th><td class="mono">{{ detail.id }}</td></tr>
              <tr><th>kind</th><td>{{ detail.kind }}</td></tr>
              <tr><th>mime</th><td>{{ detail.mime }}</td></tr>
              <tr><th>size</th><td>{{ humanSize(detail.size) }}</td></tr>
              <tr v-if="detail.kind !== 'image'">
                <th>characters</th><td>{{ detail.text.length }}</td>
              </tr>
              <tr><th>uploaded</th><td>{{ detail.created_at }}</td></tr>
            </tbody>
          </table>
        </div>

        <div class="card">
          <h3>Title and provenance</h3>
          <label class="field">
            <span>Title shown to the agents</span>
            <input v-model="titleDraft" />
          </label>
          <label class="field">
            <span>Provenance</span>
            <input v-model="provenanceDraft" placeholder="e.g. supplied by the researcher, 2024" />
          </label>
          <button class="primary" :disabled="busy || !dirty" @click="saveMeta">Save</button>
          <p class="hint">Editing these does not change the uploaded bytes or text.</p>
        </div>

        <div class="card">
          <h3>Used by</h3>
          <template v-if="selected?.references.workflows.length">
            <ul class="material-list">
              <li v-for="entry in selected.references.workflows" :key="entry.step_id">
                <span class="tag">{{ entry.workflow_name }} v{{ entry.workflow_version }}</span>
                <span>{{ entry.step_name }}</span>
              </li>
            </ul>
          </template>
          <p v-else class="empty">Not bound to any step.</p>
          <p class="hint">
            Used in {{ selected?.references.runs ?? 0 }} run step(s) so far.
            Deleting removes it from every step above and bumps that workflow's version.
          </p>
        </div>

        <div class="card" style="border-color: #d9c3bf">
          <h3>Delete</h3>
          <p class="hint">
            The uploaded file is removed too, unless another material shares the same bytes.
            Historical runs keep their records, but this material can no longer be opened from
            them.
          </p>
          <button class="danger" :disabled="busy" @click="removeSelected">
            {{ confirmingDelete ? 'Click again to delete permanently' : 'Delete material' }}
          </button>
          <button v-if="confirmingDelete" class="ghost" @click="confirmingDelete = false">Cancel</button>
        </div>
      </div>
      <p v-else class="empty">Select a material to preview it.</p>
    </section>
  </div>
</template>

<style scoped>
.preview-mount {
  background: var(--ink);
  padding: 14px;
  border-radius: 3px;
  max-height: 46vh;
  overflow: auto;
}

.preview-mount img {
  display: block;
  max-width: 100%;
  height: auto;
}

.preview-text {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 3px;
  padding: 14px 16px;
  max-height: 46vh;
  overflow: auto;
}

.preview-text pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: var(--serif);
  font-size: 15px;
  line-height: 1.7;
}

.meta {
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
}

.meta th {
  text-align: left;
  font-weight: 500;
  color: var(--muted);
  width: 110px;
  padding: 3px 8px 3px 0;
  vertical-align: top;
}

.meta td {
  padding: 3px 0;
}

.mono {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 12px;
}
</style>
