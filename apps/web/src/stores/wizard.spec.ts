import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useWizardStore } from '@/stores/wizard'

describe('wizard store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts with an empty draft', () => {
    const wizard = useWizardStore()
    expect(wizard.draft.config.name).toBe('')
    expect(wizard.draft.visibility).toBe('private')
  })

  it('updateConfig merges partial config changes', () => {
    const wizard = useWizardStore()
    wizard.updateConfig({ name: 'Mon agent' })
    expect(wizard.draft.config.name).toBe('Mon agent')
    expect(wizard.draft.config.temperature).toBe(0.7)
  })

  it('starts with the contract defaults for inputs and outputs', () => {
    const wizard = useWizardStore()
    expect(wizard.draft.config.inputs).toEqual(['text'])
    expect(wizard.draft.config.outputs).toEqual(['text'])
  })

  it('reset restores the initial draft', () => {
    const wizard = useWizardStore()
    wizard.updateConfig({ name: 'Mon agent' })
    wizard.reset()
    expect(wizard.draft.config.name).toBe('')
  })
})
