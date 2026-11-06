<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'
import type { Case, Material } from '../types'

const props = defineProps<{
  cases: Case[]
  activeCase: Case | null
  materials: Material[]
}>()

const emit = defineEmits<{
  (event: 'refresh-cases'): void
  (event: 'select-case', caseId: string): void
  (event: 'materials-changed'): void
  (event: 'error', message: string): void
  (event: 'continue'): void
}>()

const newTitle = ref('')
const busy = ref(false)

const imageFile = ref<File | null>(null)
const imageTitle = ref('')

const articleFile = ref<File | null>(null)
const articleText = ref('')
const articleTitle = ref('')
const articleProvenance = ref('')

async function createCase() {
  if (!newTitle.value.trim()) return
  busy.value = true
  try {
    const created = await api.createCase(newTitle.value.trim())
    emit('refresh-cases')
    emit('select-case', created.id)
    newTitle.value = ''
  } catch (err) {
    emit('error', (err as Error).message)
  } finally {
    busy.value = false
  }
}

function onImagePicked(event: Event) {
  const input = event.target as HTMLInputElement
  imageFile.value = input.files?.[0] ?? null
  if (imageFile.value && !imageTitle.value) imageTitle.value = imageFile.value.name
}

function onArticlePicked(event: Event) {
  const input = event.target as HTMLInputElement
  articleFile.value = input.files?.[0] ?? null
  if (articleFile.value && !articleTitle.value) articleTitle.value = articleFile.value.name
}

async function uploadImage() {
  if (!props.activeCase) return
  if (!imageFile.value) {
    emit('error', 'choose an image file first')
    return
  }
  const form = new FormData()
  form.append('kind', 'image')
  form.append('title', imageTitle.value)
  form.append('file', imageFile.value)
  busy.value = true
  try {
    await api.uploadMaterial(props.activeCase.id, form)
    imageFile.value = null
    imageTitle.value = ''
    emit('materials-changed')
  } catch (err) {
    emit('error', (err as Error).message)
  } finally {
    busy.value = false
  }
}

async function uploadArticle() {
  if (!props.activeCase) return
  const form = new FormData()
  form.append('kind', 'article')
  form.append('title', articleTitle.value)
  form.append('provenance', articleProvenance.value)
  if (articleText.value.trim()) form.append('pasted_text', articleText.value)
  if (articleFile.value) form.append('file', articleFile.value)
  if (!articleText.value.trim() && !articleFile.value) {
    emit('error', 'paste the article text or choose a PDF, TXT, or MD file')
    return
  }
  busy.value = true
  try {
    await api.uploadMaterial(props.activeCase.id, form)
    articleFile.value = null
    articleText.value = ''
    articleTitle.value = ''
    articleProvenance.value = ''
    emit('materials-changed')
  } catch (err) {
    emit('error', (err as Error).message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="split">
    <section class="pane">
      <h2>Prepare materials</h2>
      <p class="hint">
        Nothing is preloaded. Everything an agent can see comes from what you upload here, and only
        the steps you bind it to will receive it.
      </p>

      <div class="card">
        <h3>Case</h3>
        <div class="row" style="margin-bottom: 6px">
          <input
            v-model="newTitle"
            placeholder="Title of the work or case"
            style="flex: 1; min-width: 220px"
            @keydown.enter="createCase"
          />
          <button class="primary" :disabled="busy || !newTitle.trim()" @click="createCase">Create case</button>
        </div>
        <p class="hint" style="margin-bottom: 10px">
          <template v-if="!newTitle.trim()">Type a title to enable “Create case”, then press Enter or click the button.</template>
          <template v-else>Press Enter or click “Create case”.</template>
        </p>
        <ul v-if="cases.length" class="material-list">
          <li v-for="item in cases" :key="item.id">
            <button class="ghost" :disabled="item.id === activeCase?.id" @click="emit('select-case', item.id)">
              {{ item.id === activeCase?.id ? 'Current' : 'Open' }}
            </button>
            <span>{{ item.title }}</span>
            <span class="id">{{ item.id }}</span>
          </li>
        </ul>
        <p v-else class="empty">No cases yet.</p>
      </div>

      <div v-if="activeCase" class="card">
        <h3>Image</h3>
        <label class="field">
          <span>PNG, JPEG, or WebP</span>
          <input type="file" accept="image/png,image/jpeg,image/webp" @change="onImagePicked" />
        </label>
        <label class="field">
          <span>Title shown to the agents</span>
          <input v-model="imageTitle" placeholder="e.g. Detail of the first episode" />
        </label>
        <button :disabled="busy" @click="uploadImage">Add image</button>
        <p class="hint" style="margin-top: 8px">
          A crop is allowed. Agents are told they see only what is inside this frame.
        </p>
      </div>

      <div v-if="activeCase" class="card">
        <h3>Article or note</h3>
        <label class="field">
          <span>PDF, TXT, or MD (optional if you paste text)</span>
          <input type="file" accept=".pdf,.txt,.md" @change="onArticlePicked" />
        </label>
        <label class="field">
          <span>Title</span>
          <input v-model="articleTitle" placeholder="e.g. A note on the handscroll" />
        </label>
        <label class="field">
          <span>Provenance you want shown with it</span>
          <input v-model="articleProvenance" placeholder="e.g. supplied by the researcher, 2024" />
        </label>
        <label class="field">
          <span>Or paste the text</span>
          <textarea v-model="articleText" rows="6" placeholder="Paste the article text here"></textarea>
        </label>
        <button :disabled="busy" @click="uploadArticle">Add article</button>
        <p class="hint" style="margin-top: 8px">
          A scanned PDF has no extractable text; the backend asks you to paste the text instead.
        </p>
      </div>
    </section>

    <aside class="pane" style="border-left: 1px solid var(--line); background: #fafbf8">
      <h2>Materials in this case</h2>
      <ul v-if="materials.length" class="material-list">
        <li v-for="material in materials" :key="material.id">
          <span class="tag">{{ material.kind }}</span>
          <span style="flex: 1">{{ material.title || material.id }}</span>
          <span class="id">{{ material.id }}</span>
        </li>
      </ul>
      <p v-else class="empty">Nothing uploaded yet.</p>

      <hr style="border: none; border-top: 1px solid var(--line); margin: 16px 0" />
      <button class="primary" :disabled="!activeCase || materials.length === 0" @click="emit('continue')">
        Continue to compose →
      </button>
    </aside>
  </div>
</template>
