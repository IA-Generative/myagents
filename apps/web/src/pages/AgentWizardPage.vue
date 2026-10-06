<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { agentsApi } from '@/api/agents'
import { useAgentsStore } from '@/stores/agents'
import { useWizardStore } from '@/stores/wizard'
import WizardStepper from '@/components/wizard/WizardStepper.vue'
import StepIdentity from '@/components/wizard/StepIdentity.vue'
import StepBehavior from '@/components/wizard/StepBehavior.vue'
import StepKnowledge from '@/components/wizard/StepKnowledge.vue'
import StepTestPublish from '@/components/wizard/StepTestPublish.vue'
import type { AgentStatus } from '@/types/agent'

const STEPS = ['Identité', 'Comportement', 'Connaissances et outils', 'Test et publication']

const route = useRoute()
const router = useRouter()
const wizard = useWizardStore()
const agentsStore = useAgentsStore()

const currentStep = ref(1)
const agentId = ref<string | null>((route.params.id as string) || null)
const saving = ref(false)
const error = ref<string | null>(null)
const fromOnboarding = ref(false)

const nextBlocked = computed(() => currentStep.value === 2 && !wizard.promptValidated)

onMounted(async () => {
  wizard.reset()
  if (agentId.value) {
    const agent = await agentsApi.get(agentId.value)
    wizard.load({
      visibility: agent.visibility,
      category: agent.category,
      tags: agent.tags,
      config: agent.config,
    })
  } else {
    const raw = route.query.onboarding
    if (typeof raw === 'string') {
      // La config (potentiellement > 20 Ko) est passée via sessionStorage,
      // non via la query string, pour éviter de dépasser la limite d'URL.
      const stored = sessionStorage.getItem('onboarding_agent_config')
      if (stored) {
        try {
          const cfg = JSON.parse(stored)
          wizard.updateConfig({
            name: cfg.name ?? '',
            description: cfg.description ?? '',
            category: cfg.category ?? '',
            system_prompt: cfg.system_prompt ?? '',
            greeting: cfg.greeting ?? '',
            examples: Array.isArray(cfg.examples) ? cfg.examples : [],
          })
          fromOnboarding.value = true
        } catch {
          // ignore malformed onboarding payload
        } finally {
          sessionStorage.removeItem('onboarding_agent_config')
        }
      }
    }
  }
})

async function persist(status: AgentStatus) {
  saving.value = true
  error.value = null
  try {
    const payload = {
      visibility: wizard.draft.visibility,
      status,
      category: wizard.draft.category,
      tags: wizard.draft.tags,
      config: wizard.draft.config,
    }
    const wasCreate = !agentId.value
    if (agentId.value) {
      await agentsStore.update(agentId.value, payload)
    } else {
      const created = await agentsStore.create(payload)
      agentId.value = created.id
    }
    if (status !== 'draft') {
      router.push({ name: 'agents', query: { saved: wasCreate ? status : 'updated' } })
    }
  } catch {
    error.value = "L'enregistrement a échoué. Réessayez."
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <h1>{{ agentId ? "Modifier l'agent" : 'Créer un agent' }}</h1>

    <div v-if="fromOnboarding" class="fr-alert fr-alert--info fr-mb-4w">
      <p>
        L'assistant a pré-rempli les champs à partir de vos réponses. Vérifiez et ajustez si
        nécessaire, puis passez à l'étape suivante.
      </p>
    </div>

    <WizardStepper :steps="STEPS" :current="currentStep" />

    <p v-if="error" class="fr-alert fr-alert--error fr-mt-2w">{{ error }}</p>

    <section class="fr-mt-4w">
      <StepIdentity v-if="currentStep === 1" />
      <StepBehavior v-else-if="currentStep === 2" />
      <StepKnowledge v-else-if="currentStep === 3" />
      <StepTestPublish v-else :agent-id="agentId" @publish="persist" />
    </section>

    <div class="fr-btns-group fr-btns-group--inline fr-mt-4w">
      <button
        class="fr-btn fr-btn--secondary"
        :disabled="currentStep === 1"
        @click="currentStep--"
      >
        Précédent
      </button>
      <button
        v-if="currentStep < STEPS.length"
        class="fr-btn"
        :disabled="saving || nextBlocked"
        @click="currentStep++"
      >
        Suivant
      </button>
    </div>
    <p v-if="nextBlocked" class="fr-hint-text fr-mt-1w">
      Validez les instructions système pour continuer.
    </p>
  </div>
</template>
