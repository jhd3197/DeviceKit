// Settings omnisearch index (plan 26, phase 2) — the flat catalog the command palette
// searches to deep-link individual settings.
//
// One entry per meaningful card/section across all 14 Settings panes. Each `id` is a stable
// kebab-case slug that is BOTH the palette search result and the DOM registration key: a pane
// attaches `register(id)` to the element, and the palette navigates to
// `/settings/<tab>?focus=setting:<id>` so `useSettingFocus` can scroll it into view and flash
// it. Keep `id`s in lockstep with the `reg('<id>')` calls in components/settings/*.jsx.
//
// `adminOnly` mirrors the Settings.jsx TABS `admin` flag (users/apikeys/vault/audit) plus any
// individually admin-gated card, so the palette can hide entries a non-admin can't reach.

export const SETTINGS_INDEX = [
  // --- General (tab: general) ---
  {
    id: 'instance-name',
    label: 'Instance name',
    description: 'Rename this DeviceKit node; shown in the sidebar and page titles.',
    keywords: 'instance name rename node title hostname branding label',
    tab: 'general',
    adminOnly: false,
  },
  {
    id: 'device-timeout',
    label: 'Default device timeout',
    description: 'Fallback per-command dispatch timeout for device operations.',
    keywords: 'default device timeout dispatch command seconds fleet',
    tab: 'general',
    adminOnly: false,
  },

  // --- API Access (tab: api) ---
  {
    id: 'api-key',
    label: 'API key',
    description: 'The X-API-Key this browser sends with every request.',
    keywords: 'api key x-api-key token auth header browser localstorage',
    tab: 'api',
    adminOnly: false,
  },

  // --- Account & 2FA / Security (tab: account) ---
  {
    id: 'two-factor-auth',
    label: 'Two-factor authentication',
    description: 'Enroll or disable TOTP two-factor authentication for your account.',
    keywords: 'two factor authentication 2fa totp mfa authenticator security backup codes',
    tab: 'account',
    adminOnly: false,
  },
  {
    id: 'sign-out',
    label: 'Sign out',
    description: 'End your current session on this browser.',
    keywords: 'sign out logout session end account',
    tab: 'account',
    adminOnly: false,
  },

  // --- Users & Invitations (tab: users, admin) ---
  {
    id: 'users-accounts',
    label: 'User accounts',
    description: 'Manage local accounts, roles, and per-user permissions.',
    keywords: 'users accounts roles permissions add user password reset rbac members',
    tab: 'users',
    adminOnly: true,
  },
  {
    id: 'user-invitations',
    label: 'Invitations',
    description: 'Create and revoke invitation links for new users.',
    keywords: 'invitations invite link email onboard new user revoke',
    tab: 'users',
    adminOnly: true,
  },

  // --- API Keys (tab: apikeys, admin) ---
  {
    id: 'api-keys',
    label: 'Server API keys',
    description: 'Create, rotate, and revoke scoped server-issued API keys.',
    keywords: 'api keys scoped revoke rotate create dk_ server tokens scopes programmatic',
    tab: 'apikeys',
    adminOnly: true,
  },

  // --- Workspaces (tab: workspaces) ---
  {
    id: 'active-workspace',
    label: 'Active workspace',
    description: 'The workspace this browser scopes requests to via X-Workspace-Id.',
    keywords: 'active workspace switch scope x-workspace-id current',
    tab: 'workspaces',
    adminOnly: false,
  },
  {
    id: 'workspaces',
    label: 'Workspaces',
    description: 'Create workspaces and manage their members and roles.',
    keywords: 'workspaces create delete members roles owner admin member viewer teams',
    tab: 'workspaces',
    adminOnly: false,
  },

  // --- Secrets Vault (tab: vault, admin) ---
  {
    id: 'vault-secrets',
    label: 'Secrets vault',
    description: 'Encrypted vaults for secrets used by automations and agents.',
    keywords: 'vault secrets encrypted fernet reveal keys credentials passwords storage',
    tab: 'vault',
    adminOnly: true,
  },

  // --- Audit Log (tab: audit, admin) ---
  {
    id: 'audit-log',
    label: 'Audit log',
    description: 'Read-only trail of security-relevant backend actions.',
    keywords: 'audit log trail security events who did what history compliance',
    tab: 'audit',
    adminOnly: true,
  },

  // --- AI (tab: ai) ---
  {
    id: 'ai-backend',
    label: 'AI backend',
    description: 'Choose direct provider keys or a Prompture Hub gateway.',
    keywords: 'ai backend prompture hub direct provider gateway model routing',
    tab: 'ai',
    adminOnly: false,
  },
  {
    id: 'ai-hub-url',
    label: 'Hub URL',
    description: 'Where the Prompture Hub gateway is running.',
    keywords: 'hub url prompture gateway endpoint address probe',
    tab: 'ai',
    adminOnly: false,
  },
  {
    id: 'ai-default-model',
    label: 'Default model',
    description: 'Model used across every AI feature unless overridden.',
    keywords: 'ai default model claude gpt gemini llm prompture',
    tab: 'ai',
    adminOnly: false,
  },
  {
    id: 'ai-model-overrides',
    label: 'Per-feature model overrides',
    description: 'Override the model per AI feature (generation, self-heal, analysis).',
    keywords: 'ai model overrides per feature generation self heal analysis',
    tab: 'ai',
    adminOnly: false,
  },
  {
    id: 'ai-provider-keys',
    label: 'AI provider keys',
    description: 'Store Anthropic, OpenAI, and Gemini API keys server-side.',
    keywords: 'ai provider keys anthropic openai gemini api secret credentials',
    tab: 'ai',
    adminOnly: false,
  },

  // --- Streaming (tab: streaming) ---
  {
    id: 'stream-fps',
    label: 'Default frame rate',
    description: 'Frames per second for new device streams.',
    keywords: 'streaming frame rate fps default stream video',
    tab: 'streaming',
    adminOnly: false,
  },
  {
    id: 'stream-quality',
    label: 'Default quality',
    description: 'JPEG quality for new device streams.',
    keywords: 'streaming quality jpeg bandwidth default stream compression',
    tab: 'streaming',
    adminOnly: false,
  },
  {
    id: 'recording-retention',
    label: 'Recording retention',
    description: 'How long recorded stream sessions are kept before cleanup.',
    keywords: 'recording retention days keep cleanup streaming sessions delete',
    tab: 'streaming',
    adminOnly: false,
  },

  // --- Debug Bundles (tab: bundles) ---
  {
    id: 'retention',
    label: 'Debug bundle retention',
    description: 'How long debug bundles are kept before the cleanup pass deletes them.',
    keywords: 'retention debug bundle days keep cleanup delete expiry window',
    tab: 'bundles',
    adminOnly: false,
  },
  {
    id: 'share-link-lifetime',
    label: 'Share-link lifetime',
    description: 'Default expiry for a debug bundle share link.',
    keywords: 'share link lifetime expiry bundle token minutes default',
    tab: 'bundles',
    adminOnly: false,
  },

  // --- Notifications (tab: notifications) ---
  {
    id: 'notification-channels',
    label: 'Notification channels',
    description: 'Configure delivery channels for fleet notifications.',
    keywords: 'notification channels delivery email slack webhook config alerts',
    tab: 'notifications',
    adminOnly: false,
  },
  {
    id: 'notification-preferences',
    label: 'Notification preferences',
    description: 'Per-event notification preferences.',
    keywords: 'notification preferences per event subscribe alerts fleet',
    tab: 'notifications',
    adminOnly: false,
  },

  // --- Appearance (tab: appearance) ---
  {
    id: 'accent-color',
    label: 'Accent color',
    description: 'Personalize the accent color used across DeviceKit.',
    keywords: 'accent color theme appearance personalize hue palette branding',
    tab: 'appearance',
    adminOnly: false,
  },

  // --- About (tab: about) ---
  {
    id: 'about-version',
    label: 'Version & build info',
    description: 'App version, extension SDK, and backend connection status.',
    keywords: 'about version build sdk backend health info instance',
    tab: 'about',
    adminOnly: false,
  },
]

// Entries that live in a given Settings tab. Handy for an optional lint that checks every
// indexed id is actually registered by that tab's pane.
export function settingEntriesForTab(tab) {
  return SETTINGS_INDEX.filter((e) => e.tab === tab)
}
