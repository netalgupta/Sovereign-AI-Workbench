export const landingConfig = {
  introStorageKey: 'mrpl_intro_seen',
  heroAsset: '/landing/refinery-background.png',
  introSteps: [
    'initializing local intelligence',
    'knowledge layer',
    'retrieval layer',
    'agent layer',
    'verification layer',
  ],
  introStepDurationMs: 480,
  transitionDurationMs: 420,
  greetings: {
    morning: {
      title: 'good morning, Netal.',
      detail: 'the day shift is taking shape. your local intelligence is ready.',
    },
    afternoon: {
      title: 'good afternoon, Netal.',
      detail: 'all systems are standing by. what are we investigating?',
    },
    evening: {
      title: 'still working, Netal?',
      detail: 'the refinery is quiet. your workspace is ready.',
    },
    night: {
      title: 'still awake, Netal?',
      detail: 'your local intelligence layer is here when you need it.',
    },
  },
  quickActions: [
    {
      label: 'Trace a pipeline incident',
      detail: 'investigate connected assets and records',
      query: 'Trace a pipeline incident using the local knowledge base. Identify connected assets, relevant events, and cite the source records.',
    },
    {
      label: 'Search maintenance records',
      detail: 'find procedures, inspections, and history',
      query: 'Search the local knowledge base for maintenance records relevant to my investigation. Summarize the findings and cite the source documents.',
    },
    {
      label: 'Calculate hydrogen balance',
      detail: 'work through a process calculation',
      query: 'Help me calculate the hydrogen balance. Ask for any missing stream rates, compositions, and operating conditions before calculating.',
    },
    {
      label: 'Explore the knowledge graph',
      detail: 'open connected equipment and documents',
      route: '/graph',
    },
  ],
  animation: {
    introDurationMs: 2400,
    revealDelayMs: 1100,
  },
}

export function getTimeGreeting(date = new Date()) {
  const hour = date.getHours()
  if (hour >= 5 && hour < 12) return landingConfig.greetings.morning
  if (hour >= 12 && hour < 18) return landingConfig.greetings.afternoon
  if (hour >= 18) return landingConfig.greetings.evening
  return landingConfig.greetings.night
}