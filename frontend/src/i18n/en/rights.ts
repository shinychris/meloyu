/** rights 命名空间：合规与权利中心（RightsView）。v0.7.0「去虚还实」：
 *  checklist 只陈述真实能力；原三个摆设开关整段下架，改为静态授权说明。 */
export const rightsEn = {
  // 页头
  'rights.label': 'Rights / Compliance & Rights Center',
  'rights.title': 'Every song comes with clean provenance',
  // 授权证书卡
  'rights.cert.cardTitle': 'License Certificate',
  'rights.cert.noWorks': 'No works yet',
  'rights.cert.loading': 'Loading certificate…',
  'rights.cert.viewHint': 'Click to view and issue the license certificate',
  'rights.cert.realtimeNote':
    'Certificates are issued in real time: each view creates a new issuance record and audit-trail event, and freezes the SHA-256 fingerprint of the current version; the same version is not issued twice within this session.',
  'rights.cert.errorNotAdopted': 'This version has no adopted candidate yet, so no certificate can be issued',
  'rights.cert.errorHint':
    'Adopt a candidate as the final version on the work detail page, then the license certificate can be issued.',
  'rights.cert.view': 'View certificate',
  'rights.cert.download': 'Download certificate JSON',
  'rights.cert.downloadStarted': 'Certificate JSON download started',
  'rights.cert.copyLink': 'Copy verification link',
  'rights.cert.linkCopied': 'Verification link copied',
  'rights.cert.copyFailed': 'Copy failed — please copy manually: {link}',
  // 证书字段
  'rights.field.workId': 'Work ID',
  'rights.field.modelVersion': 'Model / Version',
  'rights.field.generatedAt': 'Generated at',
  'rights.field.licenseType': 'License type',
  'rights.field.humanTrail': 'Human creative audit trail',
  'rights.field.fingerprint': 'Content fingerprint',
  'rights.license.commercial': 'Commercial license',
  'rights.license.nonCommercial': 'Non-commercial',
  'rights.trail.count': '{n} events in total',
  // 空状态
  'rights.empty':
    'No works in your library yet — create your first song in the Studio, then come back to issue a certificate.',
  // 发行合规检查（v0.7.0：真实数据驱动，只陈述实际存在的能力）
  'rights.check.title': 'Release compliance check',
  'rights.check.disclosure': 'AI generation disclosure written into every license certificate',
  'rights.check.fingerprint': 'SHA-256 fingerprint registered for every work (master / preview)',
  'rights.check.loudness': '−14 LUFS is the export target spec, not measured per track',
  'rights.check.safety': 'Built-in basic sensitive-word filtering (extensible operations wordlists)',
  // 授权说明（替代原三个摆设开关；商用权利跟随通道模型许可）
  'rights.licenseNotes.title': 'Licensing notes',
  'rights.licenseNotes.intro': 'Commercial rights follow the model license of the channel that generated the work:',
  'rights.licenseNotes.commercial': 'Commercial-use channels: local synthesis engine · ACE-Step (MIT) · Apache-2.0 models',
  'rights.licenseNotes.nonCommercial': 'Non-commercial: MusicGen (CC-BY-NC weights) · SongGeneration (Tencent academic license)',
  'rights.licenseNotes.conditional': 'Conditional: MiniMax / Stable Audio — subject to the revenue threshold in their community licenses',
  'rights.settingsNote':
    'Certificates are issued by the system: AI disclosure, human participation audit trail and SHA-256 fingerprint are frozen with each work version. PDF certificates arrive in V1.1.',
} as const
