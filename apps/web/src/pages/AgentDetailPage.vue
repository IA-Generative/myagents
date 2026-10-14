<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { catalogApi } from '@/api/catalog'
import { agentsApi } from '@/api/agents'
import { ratingsApi } from '@/api/ratings'
import { favoritesApi } from '@/api/favorites'
import VisibilityBadge from '@/components/VisibilityBadge.vue'
import AgentChatWidget from '@/components/AgentChatWidget.vue'
import type { AgentDetail, Rating } from '@/types/agent'

const props = defineProps<{ id: string }>()
const router = useRouter()

const agent = ref<AgentDetail | null>(null)
const ratings = ref<Rating[]>([])
const score = ref(5)
const comment = ref('')
const isFavorite = ref(false)
const forking = ref(false)

async function load() {
  agent.value = await catalogApi.get(props.id)
  ratings.value = await ratingsApi.list(props.id)
  const favorites = await favoritesApi.list()
  isFavorite.value = favorites.some((f) => f.agent_id === props.id)
}

onMounted(load)

async function submitRating() {
  await ratingsApi.rate(props.id, score.value, comment.value || undefined)
  ratings.value = await ratingsApi.list(props.id)
  comment.value = ''
}

async function toggleFavorite() {
  if (isFavorite.value) {
    await favoritesApi.remove(props.id)
  } else {
    await favoritesApi.add(props.id)
  }
  isFavorite.value = !isFavorite.value
}

async function duplicate() {
  forking.value = true
  try {
    const forked = await agentsApi.fork(props.id)
    router.push({ name: 'agent-edit', params: { id: forked.id } })
  } finally {
    forking.value = false
  }
}
</script>

<template>
  <div v-if="agent">
    <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap">
      <h1 class="fr-mb-0">{{ agent.config.name }}</h1>
      <VisibilityBadge :visibility="agent.visibility" />
    </div>
    <p>{{ agent.config.description }}</p>

    <div class="fr-btns-group fr-btns-group--inline fr-mb-4w">
      <button class="fr-btn fr-btn--secondary" @click="toggleFavorite">
        {{ isFavorite ? 'Retirer des favoris' : 'Ajouter aux favoris' }}
      </button>
      <button class="fr-btn fr-btn--secondary" :disabled="forking" @click="duplicate">
        Dupliquer pour le personnaliser
      </button>
    </div>

    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-12 fr-col-md-6">
        <h2 class="fr-h5">Discuter avec cet agent</h2>
        <AgentChatWidget
          :agent-name="agent.config.name"
          :greeting="agent.config.greeting"
          :send="(msgs) => catalogApi.chat(props.id, msgs)"
        />
      </div>

      <div class="fr-col-12 fr-col-md-6">
        <h2 class="fr-h5">Notes ({{ ratings.length }})</h2>
        <ul>
          <li v-for="r in ratings" :key="r.id">{{ r.score }}/5 — {{ r.comment }}</li>
        </ul>

        <div class="fr-input-group fr-mt-2w">
          <label class="fr-label" for="score">Votre note</label>
          <select id="score" v-model.number="score" class="fr-select">
            <option v-for="n in [1, 2, 3, 4, 5]" :key="n" :value="n">{{ n }}</option>
          </select>
          <input v-model="comment" class="fr-input fr-mt-1w" type="text" placeholder="Commentaire (optionnel)">
          <button class="fr-btn fr-mt-2w" @click="submitRating">Envoyer la note</button>
        </div>
      </div>
    </div>
  </div>
</template>
